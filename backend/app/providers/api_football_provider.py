"""api-football（API-Sports v3）真实数据 Provider。

文档: https://www.api-football.com/documentation-v3
鉴权: 请求头 x-apisports-key
端点映射:
    fixtures            -> /fixtures?date=YYYY-MM-DD / &live=all
    events              -> /fixtures/events?fixture={id}
    statistics          -> /fixtures/statistics?fixture={id}

设计说明：真实 API 的 fixture id 与本地数据库 id 不同空间，
本适配器负责 id 透传与字段映射；接入真实数据后由同步任务
（upsert 队伍/比赛）将外部数据写入本地库（幂等键见 db/schema.sql）。
"""
import json
import urllib.error
import urllib.request
from typing import Any

from app.core.config import settings
from app.providers.base import FootballDataProvider


class ApiFootballProvider(FootballDataProvider):
    name = "api_football"

    def __init__(self, api_key: str | None = None) -> None:
        self._key = api_key or settings.API_FOOTBALL_KEY
        if not self._key:
            raise ValueError("API_FOOTBALL_KEY 未配置（环境变量）")

    # ---------------- 内部 ----------------
    def _get(self, path: str, params: dict[str, str] | None = None) -> dict:
        qs = ("?" + "&".join(f"{k}={v}" for k, v in (params or {}).items())) or ""
        req = urllib.request.Request(
            f"{settings.API_FOOTBALL_BASE}{path}{qs}",
            headers={"x-apisports-key": self._key},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise RuntimeError(f"api-football 请求失败: {e}") from e

    # ---------------- 接口实现 ----------------
    def fixtures(self, days: int = 3) -> list[dict[str, Any]]:
        from datetime import date, timedelta

        out: list[dict[str, Any]] = []
        for offset in range(-2, days - 2 + 1):
            d = (date.today() + timedelta(days=offset)).isoformat()
            payload = self._get("/fixtures", {"date": d})
            for f in payload.get("response", []):
                fx = f["fixture"]
                out.append({
                    "external_id": fx["id"],
                    "league": f["league"]["name"],
                    "home_team": f["teams"]["home"]["name"],
                    "away_team": f["teams"]["away"]["name"],
                    "kickoff_at": fx["date"],
                    "status": fx["status"]["short"],  # 1H/HT/2H/FT/NS ...
                    "minute": fx["status"]["elapsed"],
                    "score": (
                        f["goals"]["home"], f["goals"]["away"]
                    ),
                })
        return out

    def events(self, match_id: int) -> list[dict[str, Any]]:
        payload = self._get("/fixtures/events", {"fixture": str(match_id)})
        return [
            {"minute": e["time"]["elapsed"],
             "side": "home" if e["team"]["id"] == self._side_hint else e["side"],
             "type": e["type"].lower().replace("var", "var"),
             "player": e["player"]["name"], "detail": e.get("detail", "")}
            for e in payload.get("response", [])
        ]

    def statistics(self, match_id: int) -> dict[str, Any] | None:
        payload = self._get("/fixtures/statistics", {"fixture": str(match_id)})
        rows = payload.get("response", [])
        if not rows:
            return None

        def _stat(team: dict, label: str) -> Any:
            for s in team.get("statistics", []):
                if s["type"] == label:
                    return s["value"]
            return None

        home, away = rows[0], rows[-1]
        return {
            "possession_home": _stat(home, "Ball Possession"),
            "possession_away": _stat(away, "Ball Possession"),
            "shots_home": _stat(home, "Total Shots"),
            "shots_away": _stat(away, "Total Shots"),
            "shots_on_target_home": _stat(home, "Shots on Goal"),
            "shots_on_target_away": _stat(away, "Shots on Goal"),
            "corners_home": _stat(home, "Corner Kicks"),
            "corners_away": _stat(away, "Corner Kicks"),
            "fouls_home": _stat(home, "Fouls"),
            "fouls_away": _stat(away, "Fouls"),
            "yellow_home": _stat(home, "Yellow Cards"),
            "yellow_away": _stat(away, "Yellow Cards"),
            "red_home": _stat(home, "Red Cards"),
            "red_away": _stat(away, "Red Cards"),
        }

    def healthcheck(self) -> dict[str, Any]:
        try:
            payload = self._get("/status")
            acct = payload.get("response", [{}])[0].get("account", {})
            return {
                "provider": self.name, "ok": True,
                "account": acct.get("email"), "quota_left": acct.get("quota_left"),
            }
        except Exception as e:
            return {"provider": self.name, "ok": False, "error": str(e)}


# events() 中 side 归一化用（fixture events 返回 team 对象而非主客标记）
ApiFootballProvider._side_hint = None  # type: ignore[attr-defined]
