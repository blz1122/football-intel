"""比赛相关路由：列表 / 详情 / 事件 / 统计 / 胜率曲线 / 射门地图。"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import settings
from app.core.db import get_db
from app.core.predictor import inmatch
from app.ingest.espn import zh_event_detail
from app.models import Match, MatchPrediction, TeamRating
from app.schemas import (
    CurvePoint,
    EventOut,
    LeagueBrief,
    LiveStats,
    MatchDetail,
    MatchListItem,
    MonteCarloOut,
    PredictionOut,
    ShotMap,
    ShotOut,
    TeamBrief,
    TeamRadar,
    WinProb,
)
from app.simulator import match_state, stats_series

router = APIRouter(prefix="/api/v1/matches", tags=["matches"])


# ---------------- 内部工具 ----------------
def _ratings_map(db: Session) -> dict[int, TeamRating]:
    return {r.team_id: r for r in db.query(TeamRating).all()}


def _team_brief(t, rating: TeamRating | None) -> TeamBrief:
    radar = None
    tpi = None
    if rating:
        tpi = rating.tpi
        radar = TeamRadar(
            attack=rating.attack, defense=rating.defense,
            possession=rating.possession, pressing=rating.pressing,
            efficiency=rating.efficiency, form=rating.form,
        )
    return TeamBrief(
        id=t.id, name=t.name, name_en=t.name_en, short_name=t.short_name,
        color=t.color, elo_rating=t.elo_rating, tpi=tpi, radar=radar,
    )
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


def effective_state(m: Match) -> dict:
    """真实数据源（ESPN）落库的状态优先；模拟数据按 kickoff 惰性推导。"""
    if m.status_override:
        minute = m.minute_override
        period = {"live": "2H" if (minute or 0) > 45 else "1H",
                  "halftime": "HT", "finished": "FT"}.get(m.status_override)
        return {"status": m.status_override, "period": period, "minute": minute}
    return match_state(m.kickoff_at)


def _score(m: Match, events) -> tuple[int, int]:
    """真实比分来自 provider 落库值；模拟比分由事件累计。"""
    if m.score_home is not None and m.score_away is not None:
        return m.score_home, m.score_away
    hs = sum(1 for e in events if e.type == "goal" and e.side == "home")
    as_ = sum(1 for e in events if e.type == "goal" and e.side == "away")
    return hs, as_


def _goal_minutes(events) -> tuple[list[int], list[int]]:
    gh = [e.minute for e in events if e.type == "goal" and e.side == "home"]
    ga = [e.minute for e in events if e.type == "goal" and e.side == "away"]
    return gh, ga


def _win_prob(m: Match, state: dict, hs: int, as_: int, pred: MatchPrediction) -> WinProb:
    # 赛前预测：直接用模型输出
    if state["status"] == "scheduled":
        return WinProb(home=pred.p_home, draw=pred.p_draw, away=pred.p_away)
    # 已结束：展示赛前预测而非赛后重算。
    # 真实数据源下 lambda 可能很小（强弱悬殊），inmatch() 代入终场比分会算出 0/1/0
    # 这种无意义的极端值；赛前概率才是"AI 预测 vs 实际"有意义对照。
    if state["status"] == "finished":
        return WinProb(home=pred.p_home, draw=pred.p_draw, away=pred.p_away)
    p = inmatch(state["minute"] or 90, hs, as_, pred.lambda_home, pred.lambda_away)
    return WinProb(home=p["p_home"], draw=p["p_draw"], away=p["p_away"])


def _live_stats(m: Match, state: dict, events) -> LiveStats | None:
    if state["status"] == "scheduled":
        return None
    # 真实数据源：直接采用 ESPN boxscore 落库的统计
    if m.stats_json:
        d = dict(m.stats_json)
        d["minute"] = state["minute"] or d.get("minute") or 90
        d.setdefault("dangerous_home", 0)
        d.setdefault("dangerous_away", 0)
        return LiveStats(**d)
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


def _to_item(m: Match, state: dict, hot: bool,
             ratings: dict[int, TeamRating] | None = None) -> MatchListItem:
    events = _visible_events(m, state)
    hs, as_ = _score(m, events)
    pred = m.prediction
    ratings = ratings or {}
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
        home_team=_team_brief(m.home_team, ratings.get(m.home_team_id)),
        away_team=_team_brief(m.away_team, ratings.get(m.away_team_id)),
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
    """比赛列表。返回近 7 日 + 未来 `MATCH_WINDOW_DAYS` 日窗口内全部比赛。

    窗口放宽是因为真实数据源（ESPN）的赛程可能跨周，且欧冠/世预赛等赛事
    常在 10 天后才开赛——窗口太小会让"即将开始"看起来空空的。"""
    now = datetime.now(timezone.utc)
    q = (
        db.query(Match)
        .filter(
            Match.is_history.is_(False),
            Match.kickoff_at >= now - timedelta(days=7),
            Match.kickoff_at <= now + timedelta(days=settings.MATCH_WINDOW_DAYS),
        )
    )
    if league_id:
        q = q.filter(Match.league_id == league_id)
    matches = (
        q.options(
            joinedload(Match.league),
            joinedload(Match.home_team),
            joinedload(Match.away_team),
            joinedload(Match.prediction),
            selectinload(Match.events),
        )
        .order_by(Match.kickoff_at)
        .all()
    )
    ratings = _ratings_map(db)

    # 焦点战：未开赛场次中 Elo 之和最高的 6 场
    scheduled = [m for m in matches if effective_state(m)["status"] == "scheduled"]
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
        state = effective_state(m)
        if status and state["status"] != status:
            continue
        items.append(_to_item(m, state, m.id in hot_ids, ratings))
    return items


@router.get("/{match_id}", response_model=MatchDetail)
def match_detail(match_id: int, db: Session = Depends(get_db)):
    m = _get_match(db, match_id)
    state = effective_state(m)
    events = _visible_events(m, state)
    item = _to_item(m, state, False, _ratings_map(db))
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
                player_id=e.player_id, player=_name(e.player_id),
                related_player_id=e.related_player_id,
                related_player=_name(e.related_player_id),
                detail=e.detail,
                detail_cn=zh_event_detail(e.detail, e.type),
            )
            for e in events
        ],
        prediction=pred,
    )


@router.get("/{match_id}/statistics")
def match_statistics(match_id: int, db: Session = Depends(get_db)):
    """分钟级统计序列（进行中返回截至当前分钟）。"""
    m = _get_match(db, match_id)
    state = effective_state(m)
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
    state = effective_state(m)
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
    state = effective_state(m)
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


@router.get("/{match_id}/report")
def match_report(match_id: int, db: Session = Depends(get_db)):
    """AI 比赛报告：数据驱动模板引擎（默认）或 LLM 生成（可选），10 秒缓存。"""
    from app.core.cache import cache
    from app.core.report import build_facts, generate_report

    m = _get_match(db, match_id)
    state = effective_state(m)
    events = _visible_events(m, state)
    hs, as_ = _score(m, events)
    state = {**state, "home_score": hs, "away_score": as_}
    stats = _live_stats(m, state, events)
    if not m.prediction:
        raise HTTPException(404, "MODEL_NOT_READY")

    curve = None
    if state["status"] != "scheduled":
        cached_curve = cache.get(f"curve:{match_id}:{state['minute']}")
        if cached_curve is None:
            pred = m.prediction
            gh, ga = _goal_minutes(events)
            pts, h, a = [], 0, 0
            for minute in range(1, (state["minute"] or 90) + 1):
                if minute in gh:
                    h += 1
                if minute in ga:
                    a += 1
                pts.append({"minute": minute, **inmatch(
                    minute, h, a, pred.lambda_home, pred.lambda_away)})
            cached_curve = pts
            cache.set(f"curve:{match_id}:{state['minute']}", cached_curve, 10)
        curve = cached_curve

    facts = build_facts(m, state, events, stats, m.prediction, curve)
    result = generate_report(facts)
    return {"match_id": match_id, "generated_at": state["minute"], **result}


@router.get("/{match_id}/monte-carlo", response_model=MonteCarloOut)
def monte_carlo(match_id: int, simulations: int = 10000, db: Session = Depends(get_db)):
    """Monte Carlo 比赛模拟：10,000 次采样 -> 比分矩阵 / 大小球 / BTTS。
    结果按 (match_id, simulations) 缓存。"""
    from fastapi import HTTPException as _HE

    from app.ml.monte_carlo import simulate
    from app.models import MonteCarloResult

    if not (1000 <= simulations <= 50000):
        raise _HE(400, "simulations 必须在 1000-50000 之间")
    m = _get_match(db, match_id)
    if not m.prediction or not m.prediction.score_matrix:
        raise _HE(404, "MODEL_NOT_READY")

    cached = (
        db.query(MonteCarloResult)
        .filter(MonteCarloResult.match_id == match_id,
                MonteCarloResult.simulations == simulations)
        .first()
    )
    if cached:
        return MonteCarloOut(
            match_id=match_id, simulations=cached.simulations,
            p_home=cached.p_home, p_draw=cached.p_draw, p_away=cached.p_away,
            score_matrix=cached.score_matrix, over_under=cached.over_under,
            btts=cached.btts, model_version=cached.model_version,
        )

    result = simulate(m.prediction.score_matrix, n=simulations, seed=m.sim_seed)
    row = MonteCarloResult(
        match_id=match_id, simulations=simulations,
        p_home=result["p_home"], p_draw=result["p_draw"], p_away=result["p_away"],
        score_matrix=result["score_matrix"], over_under=result["over_under"],
        btts=result["btts"],
    )
    db.add(row)
    db.commit()
    return MonteCarloOut(match_id=match_id, simulations=simulations,
                         model_version=row.model_version, **result)
