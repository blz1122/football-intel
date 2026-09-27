"""元信息路由：Dashboard KPI / AI 预测排行 / 联赛列表。"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import League, Match
from app.schemas import Kpis, PredictionRankItem
from app.simulator import match_state

router = APIRouter(prefix="/api/v1/meta", tags=["meta"])


def _today_window_utc() -> tuple[datetime, datetime]:
    """北京时间当天的 UTC 窗口。"""
    now_local = datetime.now(timezone.utc) + timedelta(hours=8)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    start = start_local - timedelta(hours=8)
    return start, start + timedelta(days=1)


@router.get("/leagues")
def leagues(db: Session = Depends(get_db)):
    return [
        {"id": l.id, "name": l.name, "short_name": l.short_name, "country": l.country}
        for l in db.query(League).order_by(League.id).all()
    ]


@router.get("/kpis", response_model=Kpis)
def kpis(db: Session = Depends(get_db)):
    start, end = _today_window_utc()
    today = db.query(Match).filter(Match.kickoff_at >= start, Match.kickoff_at < end).all()
    live = sum(1 for m in today if match_state(m.kickoff_at)["status"] in ("live", "halftime"))
    finished = sum(1 for m in today if match_state(m.kickoff_at)["status"] == "finished")

    # 近 7 日已完赛比赛的模型评估（真实计算而非硬编码）
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    done = (
        db.query(Match)
        .filter(Match.kickoff_at >= cutoff, Match.kickoff_at < datetime.now(timezone.utc))
        .all()
    )
    hits, n, brier = 0, 0, 0.0
    for m in done:
        st = match_state(m.kickoff_at)
        if st["status"] != "finished" or not m.prediction:
            continue
        events = m.events
        hs = sum(1 for e in events if e.type == "goal" and e.side == "home")
        as_ = sum(1 for e in events if e.type == "goal" and e.side == "away")
        p = m.prediction
        probs = (p.p_home, p.p_draw, p.p_away)
        actual = (hs > as_, hs == as_, hs < as_)
        pick = max(range(3), key=lambda i: probs[i])
        hits += int(actual[pick])
        brier += sum((probs[i] - actual[i]) ** 2 for i in range(3)) / 3
        n += 1
    return Kpis(
        total_today=len(today),
        live_now=live,
        finished_today=finished,
        accuracy_7d=round(hits / n * 100, 1) if n else 0.0,
        brier_score=round(brier / n, 3) if n else 0.0,
    )


@router.get("/predictions/top", response_model=list[PredictionRankItem])
def top_predictions(db: Session = Depends(get_db)):
    """今日未开赛比赛按模型置信度排行。"""
    start, end = _today_window_utc()
    now = datetime.now(timezone.utc)
    rows = (
        db.query(Match)
        .filter(Match.kickoff_at >= max(start, now), Match.kickoff_at < end)
        .all()
    )
    items = []
    for m in rows:
        if not m.prediction:
            continue
        p = m.prediction
        probs = (p.p_home, p.p_draw, p.p_away)
        pick_i = max(range(3), key=lambda i: probs[i])
        pick = [f"{m.home_team.name} 胜", "平局", f"{m.away_team.name} 胜"][pick_i]
        items.append(PredictionRankItem(
            match_id=m.id,
            title=f"{m.home_team.short_name} vs {m.away_team.short_name}",
            pick=pick,
            probability=probs[pick_i],
            kickoff_at=m.kickoff_at,
        ))
    items.sort(key=lambda x: x.probability, reverse=True)
    return items[:6]
