"""本地模拟数据 Provider —— 封装 Phase 2/3 的确定性模拟引擎。

保留确定性种子能力：同一比赛在任何时刻重放结果一致，
便于前端开发、模型评估与演示。
"""
from typing import Any

from app.providers.base import FootballDataProvider
from app.simulator import match_state


class MockProvider(FootballDataProvider):
    name = "mock"

    def __init__(self, db_factory) -> None:
        # db_factory: () -> Session，避免跨线程共享 Session
        self._db_factory = db_factory

    def fixtures(self, days: int = 3) -> list[dict[str, Any]]:
        from datetime import datetime, timedelta, timezone

        from app.models import Match

        db = self._db_factory()
        try:
            now = datetime.now(timezone.utc)
            rows = (
                db.query(Match)
                .filter(
                    Match.kickoff_at >= now - timedelta(days=days),
                    Match.kickoff_at <= now + timedelta(days=days),
                )
                .order_by(Match.kickoff_at)
                .all()
            )
            out = []
            for m in rows:
                st = match_state(m.kickoff_at)
                out.append({
                    "id": m.id, "league_id": m.league_id,
                    "home_team_id": m.home_team_id, "away_team_id": m.away_team_id,
                    "kickoff_at": m.kickoff_at.isoformat(), "status": st["status"],
                    "minute": st["minute"], "sim_seed": m.sim_seed,
                })
            return out
        finally:
            db.close()

    def events(self, match_id: int) -> list[dict[str, Any]]:
        from app.models import MatchEvent

        db = self._db_factory()
        try:
            return [
                {"minute": e.minute, "side": e.side, "type": e.type,
                 "player_id": e.player_id, "detail": e.detail}
                for e in db.query(MatchEvent)
                .filter(MatchEvent.match_id == match_id)
                .order_by(MatchEvent.minute)
            ]
        finally:
            db.close()

    def statistics(self, match_id: int) -> dict[str, Any] | None:
        # 实时统计由路由层按 sim_seed 推导，这里返回种子与状态供其计算
        from app.models import Match

        db = self._db_factory()
        try:
            m = db.get(Match, match_id)
            if not m:
                return None
            st = match_state(m.kickoff_at)
            if st["status"] == "scheduled":
                return None
            return {"minute": st["minute"] or 90, "sim_seed": m.sim_seed,
                    "elo_diff": m.home_team.elo_rating - m.away_team.elo_rating}
        finally:
            db.close()
