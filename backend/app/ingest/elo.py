"""从真实赛果反推球队 Elo 强度。

背景：ESPN 公开接口不提供球队排名/评分，新建球队只能用 1500 的默认值，
导致所有比赛的胜率预测退化成均匀分布（45/29/26），AI 预测失去意义。

方案：用同步时抓到的**真实比分**做批量 Elo 更新（标准做法）：
  1. 收集近 N 天所有已完赛比赛（含比分）
  2. 按时间顺序遍历，用实际结果（1/0.5/0）与赛前预测概率计算得分差
  3. 依 Elo 公式更新：R' = R + K * (S - E)
  4. 同一支球队跨赛事（联赛/欧冠/国家队）共享一条评级

国家队与俱乐部分开评估（competition_type='national' 独立尺度），
因为国家队一年只打几场，样本太少且对手强度体系不同。
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

BASE_ELO = 1500.0
K_FACTOR = 28.0          # 每场更新幅度
HOME_ADV = 65.0          # 主场优势（Elo 点）
MIN_MATCHES = 1          # 至少 1 场才写入评级（历史同步已积累 2 万场，样本足够）
REGRESS_TO_MEAN = 0.12   # 向均值回归比例，防止小样本球队评级虚高
MIN_ELO, MAX_ELO = 900.0, 2400.0


def _expected(r_home: float, r_away: float) -> float:
    return 1 / (1 + 10 ** ((r_away - r_home - HOME_ADV) / 400.0))


def recompute_elo(db: Session, days: int = 400) -> dict:
    """用近 N 天真实赛果重算所有真实球队的 Elo。返回统计摘要。"""
    from app.models import League, Match, Team

    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(Match)
        .filter(
            Match.provider == "espn",
            Match.kickoff_at >= since,
            Match.kickoff_at < datetime.now(timezone.utc),
            Match.score_home.isnot(None),
            Match.score_away.isnot(None),
        )
        .order_by(Match.kickoff_at)
        .all()
    )
    if not rows:
        return {"ok": False, "matches": 0, "teams": 0, "reason": "no finished matches"}

    # 国家队与俱乐部分开评估
    national = {
        l.id for l in db.query(League).filter(League.competition_type == "national").all()
    }
    ratings: dict[tuple[str, int], float] = defaultdict(lambda: BASE_ELO)
    games: dict[tuple[str, int], int] = defaultdict(int)
    # 预取球队所属尺度，避免逐场查库
    team_scope: dict[int, str] = {}
    team_elo: dict[int, float] = {}
    for t in db.query(Team).all():
        team_scope[t.id] = "national" if t.league_id in national else "club"
        team_elo[t.id] = t.elo_rating or BASE_ELO

    for m in rows:
        if m.home_team_id is None or m.away_team_id is None:
            continue
        sh = "national" if m.league_id in national else "club"
        kh, ka = (sh, m.home_team_id), (sh, m.away_team_id)
        # 首次出现的球队用库里已有评级做初值（模拟期球队有真实差异）
        ratings[kh] = team_elo.get(m.home_team_id, BASE_ELO)
        ratings[ka] = team_elo.get(m.away_team_id, BASE_ELO)
        e_h = _expected(ratings[kh], ratings[ka])
        if m.score_home > m.score_away:
            s_h = 1.0
        elif m.score_home < m.score_away:
            s_h = 0.0
        else:
            s_h = 0.5
        delta = K_FACTOR * (s_h - e_h)
        ratings[kh] += delta
        ratings[ka] -= delta
        games[kh] += 1
        games[ka] += 1

    # 写回：只更新样本足够的球队，并向均值回归
    updated = 0
    for (scope, tid), r in ratings.items():
        n = games[(scope, tid)]
        if n < MIN_MATCHES:
            continue
        adj = BASE_ELO + (r - BASE_ELO) * (1 - REGRESS_TO_MEAN)
        t = db.get(Team, tid)
        if t is None:
            continue
        t.elo_rating = round(max(MIN_ELO, min(MAX_ELO, adj)), 1)
        updated += 1
    db.commit()

    # TPI 同步为 Elo 的归一化（0-100），让球队页雷达图有实际区分度
    for (scope, tid), r in ratings.items():
        n = games[(scope, tid)]
        if n < MIN_MATCHES:
            continue
        t = db.get(Team, tid)
        if t is None:
            continue
        from app.models import TeamRating

        tr = db.query(TeamRating).filter(TeamRating.team_id == tid).first()
        if tr is None:
            continue
        tpi = max(1.0, min(99.0, (t.elo_rating - MIN_ELO) / (MAX_ELO - MIN_ELO) * 98 + 1))
        tr.tpi = round(tpi, 1)
        bd = dict(tr.breakdown or {})
        bd["elo"] = t.elo_rating
        bd["elo_games"] = n
        bd["source"] = "espn_real_results"
        tr.breakdown = bd
    db.commit()

    return {"ok": True, "matches": len(rows), "teams": updated,
            "scope": "national+club"}
