"""比赛相关路由：列表 / 详情 / 事件 / 统计 / 胜率曲线 / 射门地图。"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.predictor import inmatch
from app.models import Match, MatchPrediction
from app.schemas import (
    CurvePoint,
    EventOut,
    LeagueBrief,
    LiveStats,
    MatchDetail,
    MatchListItem,
    PredictionOut,
    ShotMap,
    ShotOut,
    TeamBrief,
    WinProb,
)
from app.simulator import match_state, stats_series

router = APIRouter(prefix="/api/v1/matches", tags=["matches"])


# ---------------- 内部工具 ----------------
def _get_match(db: Session, match_id: int) -> Match:
    m = db.get(Match, match_id)
    if not m:
        raise HTTPException(404, "MATCH_NOT_FOUND")
    return m


def _visible_events(m: Match, state: dict):
    if state["status"] == "scheduled":
        return []
    if state["status"] == "finished":
        return m.events
    return [e for e in m.events if e.minute <= (state["minute"] or 0)]


def _score(events) -> tuple[int, int]:
    hs = sum(1 for e in events if e.type == "goal" and e.side == "home")
    as_ = sum(1 for e in events if e.type == "goal" and e.side == "away")
    return hs, as_


def _goal_minutes(events) -> tuple[list[int], list[int]]:
    gh = [e.minute for e in events if e.type == "goal" and e.side == "home"]
    ga = [e.minute for e in events if e.type == "goal" and e.side == "away"]
    return gh, ga


def _win_prob(m: Match, state: dict, hs: int, as_: int, pred: MatchPrediction) -> WinProb:
    if state["status"] == "scheduled":
        return WinProb(home=pred.p_home, draw=pred.p_draw, away=pred.p_away)
    p = inmatch(state["minute"] or 90, hs, as_, pred.lambda_home, pred.lambda_away)
    return WinProb(home=p["p_home"], draw=p["p_draw"], away=p["p_away"])


def _live_stats(m: Match, state: dict, events) -> LiveStats | None:
    if state["status"] == "scheduled":
        return None
    minute = state["minute"] or 90
    gh, ga = _goal_minutes(events)
    elo_diff = m.home_team.elo_rating - m.away_team.elo_rating
    series = stats_series(m.sim_seed, minute, 1.4, 1.25, elo_diff, gh, ga)
    if not series:
        return None
    last = series[-1]
    # 红黄牌从事件累计
    vis = events
    last["yellow_home"] = sum(
        1 for e in vis if e.side == "home" and e.type == "yellow_card")
    last["yellow_away"] = sum(
        1 for e in vis if e.side == "away" and e.type == "yellow_card")
    last["red_home"] = sum(1 for e in vis if e.side == "home" and e.type == "red_card")
    last["red_away"] = sum(1 for e in vis if e.side == "away" and e.type == "red_card")
    last["minute"] = minute
    return LiveStats(**last)


def _to_item(m: Match, state: dict, hot: bool) -> MatchListItem:
    events = _visible_events(m, state)
    hs, as_ = _score(events)
    pred = m.prediction
    return MatchListItem(
        id=m.id,
        league=LeagueBrief(id=m.league.id, name=m.league.name,
                           short_name=m.league.short_name),
        round=m.round,
        kickoff_at=m.kickoff_at,
        status=state["status"],
        period=state["period"],
        minute=state["minute"],
        home_score=hs,
        away_score=as_,
        home_team=TeamBrief(
            id=m.home_team.id, name=m.home_team.name,
            short_name=m.home_team.short_name, color=m.home_team.color,
            elo_rating=m.home_team.elo_rating,
        ),
        away_team=TeamBrief(
            id=m.away_team.id, name=m.away_team.name,
            short_name=m.away_team.short_name, color=m.away_team.color,
            elo_rating=m.away_team.elo_rating,
        ),
        win_prob=_win_prob(m, state, hs, as_, pred),
        live_stats=_live_stats(m, state, events),
        is_hot=hot,
    )


# ---------------- 路由 ----------------
@router.get("", response_model=list[MatchListItem])
def list_matches(
    status: str | None = Query(None, description="scheduled/live/halftime/finished"),
    league_id: int | None = None,
    db: Session = Depends(get_db),
):
    """比赛列表。默认返回近三日窗口内全部比赛，由前端按状态分组展示。"""
    now = datetime.now(timezone.utc)
    q = (
        db.query(Match)
        .filter(
            Match.kickoff_at >= now - timedelta(days=2),
            Match.kickoff_at <= now + timedelta(days=2),
        )
    )
    if league_id:
        q = q.filter(Match.league_id == league_id)
    matches = q.order_by(Match.kickoff_at).all()

    # 焦点战：未开赛场次中 Elo 之和最高的 6 场
    scheduled = [m for m in matches if match_state(m.kickoff_at)["status"] == "scheduled"]
    hot_ids = {
        m.id
        for m in sorted(
            scheduled,
            key=lambda x: x.home_team.elo_rating + x.away_team.elo_rating,
            reverse=True,
        )[:6]
    }
    items = []
    for m in matches:
        state = match_state(m.kickoff_at)
        if status and state["status"] != status:
            continue
        items.append(_to_item(m, state, m.id in hot_ids))
    return items


@router.get("/{match_id}", response_model=MatchDetail)
def match_detail(match_id: int, db: Session = Depends(get_db)):
    m = _get_match(db, match_id)
    state = match_state(m.kickoff_at)
    events = _visible_events(m, state)
    item = _to_item(m, state, False)
    pred = None
    if m.prediction:
        pred = PredictionOut(
            model_version=m.prediction.model_version,
            p_home=m.prediction.p_home, p_draw=m.prediction.p_draw,
            p_away=m.prediction.p_away,
            lambda_home=m.prediction.lambda_home,
            lambda_away=m.prediction.lambda_away,
            confidence=m.prediction.confidence,
            expected_score=m.prediction.expected_score,
            score_matrix=m.prediction.score_matrix,
        )

    def _name(pid: int | None) -> str | None:
        if pid is None:
            return None
        for sq in (m.home_team.players, m.away_team.players):
            for p in sq:
                if p.id == pid:
                    return p.name
        return None

    return MatchDetail(
        match=item,
        events=[
            EventOut(
                minute=e.minute, side=e.side, type=e.type,
                player=_name(e.player_id), related_player=_name(e.related_player_id),
                detail=e.detail,
            )
            for e in events
        ],
        prediction=pred,
    )


@router.get("/{match_id}/statistics")
def match_statistics(match_id: int, db: Session = Depends(get_db)):
    """分钟级统计序列（进行中返回截至当前分钟）。"""
    m = _get_match(db, match_id)
    state = match_state(m.kickoff_at)
    if state["status"] == "scheduled":
        return []
    minute = state["minute"] or 90
    gh, ga = _goal_minutes(_visible_events(m, state))
    elo_diff = m.home_team.elo_rating - m.away_team.elo_rating
    return stats_series(
        m.sim_seed, minute, 1.4, 1.25, elo_diff, gh, ga
    )


@router.get("/{match_id}/win-probability/curve", response_model=list[CurvePoint])
def win_probability_curve(match_id: int, db: Session = Depends(get_db)):
    """实时胜率曲线：每分钟一个点，进球分钟标记 trigger=goal。"""
    m = _get_match(db, match_id)
    state = match_state(m.kickoff_at)
    if state["status"] == "scheduled":
        return []
    pred = m.prediction
    events = _visible_events(m, state)
    gh, ga = _goal_minutes(events)
    current = state["minute"] or 90
    points: list[CurvePoint] = []
    hs = as_ = 0
    for minute in range(1, current + 1):
        if minute in gh:
            hs += 1
        if minute in ga:
            as_ += 1
        p = inmatch(minute, hs, as_, pred.lambda_home, pred.lambda_away)
        points.append(CurvePoint(
            minute=minute, trigger="goal" if (minute in gh or minute in ga) else "minute",
            **p,
        ))
    return points


@router.get("/{match_id}/shotmap", response_model=ShotMap)
def shotmap(match_id: int, db: Session = Depends(get_db)):
    """射门地图：按种子合成射门坐标与 xG，进球标记在 xG 最高的射门上。"""
    import numpy as np

    m = _get_match(db, match_id)
    state = match_state(m.kickoff_at)
    if state["status"] == "scheduled":
        return ShotMap(home=[], away=[])
    events = _visible_events(m, state)
    stats = _live_stats(m, state, events)
    n_home = stats.shots_home if stats else 8
    n_away = stats.shots_away if stats else 6
    g_home = sum(1 for e in events if e.type == "goal" and e.side == "home")
    g_away = sum(1 for e in events if e.type == "goal" and e.side == "away")

    def _shots(n: int, goals: int, x_range: tuple[float, float], seed_off: int):
        rs = np.random.RandomState(m.sim_seed + seed_off)
        n = max(n, 1)
        xg = np.sort(rs.beta(1.6, 7.0, n))[::-1]  # 降序，头部作为进球
        xs = rs.uniform(x_range[0], x_range[1], n).round(3)
        ys = rs.uniform(0.06, 0.94, n).round(3)
        out = []
        for i in range(n):
            out.append(ShotOut(
                x=float(xs[i]), y=float(ys[i]),
                xg=round(float(xg[i]), 3), goal=i < goals,
            ))
        return out

    return ShotMap(
        home=_shots(n_home, g_home, (0.62, 0.95), 101),
        away=_shots(n_away, g_away, (0.05, 0.38), 202),
    )
