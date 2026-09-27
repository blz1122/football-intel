"""真实数据源：ESPN 公开接口（无需 API key）。

设计要点：
- scoreboard 提供联赛最近一轮 + 今日赛程（真实开球时间/状态/比分/分钟）
- summary 提供 keyEvents（进球/红黄牌/换人，含分钟与球员名）与 boxscore 技术统计
- 同步为 UPSERT：以 provider_event_id 幂等，重复执行不产生重复数据
- 同步成功后删除 provider='mock' 的模拟比赛，避免界面出现"真实世界不存在"的比赛

注意：ESPN 该端点对浏览器 UA（Mozilla/Chrome）返回 403，需使用 curl 风格 UA。
"""
from __future__ import annotations

import gzip
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

UA = "curl/8.4.0-foodball-intel"
BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# ESPN 联赛 slug -> (中文名, 英文名, 简称)
LEAGUES: dict[str, tuple[str, str, str]] = {
    "eng.1": ("英超", "Premier League", "英超"),
    "esp.1": ("西甲", "La Liga", "西甲"),
    "ita.1": ("意甲", "Serie A", "意甲"),
    "ger.1": ("德甲", "Bundesliga", "德甲"),
    "fra.1": ("法甲", "Ligue 1", "法甲"),
}

# ESPN 队名 -> 中文名（覆盖常见升降级球队；其余走 name_en 归一化匹配）
TEAM_CN: dict[str, str] = {
    # 英超
    "Manchester City": "曼城", "Manchester United": "曼联", "Liverpool": "利物浦",
    "Arsenal": "阿森纳", "Chelsea": "切尔西", "Tottenham Hotspur": "热刺",
    "Newcastle United": "纽卡斯尔", "Aston Villa": "阿斯顿维拉", "West Ham United": "西汉姆联",
    "Brighton & Hove Albion": "布莱顿", "Everton": "埃弗顿", "Wolverhampton Wanderers": "狼队",
    "AFC Bournemouth": "伯恩茅斯", "Bournemouth": "伯恩茅斯", "Leeds United": "利兹联",
    "Crystal Palace": "水晶宫", "Sunderland": "桑德兰", "Fulham": "富勒姆",
    "Nottingham Forest": "诺丁汉森林", "Brentford": "布伦特福德", "Burnley": "伯恩利",
    # 西甲
    "Real Madrid": "皇家马德里", "FC Barcelona": "巴塞罗那", "Barcelona": "巴塞罗那",
    "Atlético Madrid": "马德里竞技", "Atletico Madrid": "马德里竞技", "Sevilla": "塞维利亚",
    "Real Betis": "皇家贝蒂斯", "Villarreal": "比利亚雷亚尔", "Valencia": "瓦伦西亚",
    "Real Sociedad": "皇家社会", "Athletic Club": "毕尔巴鄂竞技", "Getafe": "赫塔菲",
    "Málaga": "马拉加", "Malaga": "马拉加", "Deportivo": "拉科鲁尼亚", "Celta Vigo": "塞尔塔",
    "Espanyol": "西班牙人", "Osasuna": "奥萨苏纳", "Rayo Vallecano": "巴列卡诺",
    "Real Valladolid": "巴拉多利德", "Girona": "赫罗纳", "Mallorca": "马略卡",
    # 意甲
    "Inter Milan": "国际米兰", "Internazionale": "国际米兰", "AC Milan": "AC米兰",
    "Juventus": "尤文图斯", "Napoli": "那不勒斯", "AS Roma": "罗马", "Roma": "罗马",
    "Lazio": "拉齐奥", "Atalanta": "亚特兰大", "Fiorentina": "佛罗伦萨", "Bologna": "博洛尼亚",
    "Torino": "都灵", "Udinese": "乌迪内斯", "Genoa": "热那亚", "Como": "科莫",
    "Frosinone": "弗罗西诺内", "Parma": "帕尔马", "Cagliari": "卡利亚里", "Lecce": "莱切",
    "Empoli": "恩波利", "Sassuolo": "萨索洛", "Verona": "维罗纳", "Monza": "蒙扎",
    # 德甲
    "Bayern Munich": "拜仁慕尼黑", "Borussia Dortmund": "多特蒙德", "RB Leipzig": "莱比锡红牛",
    "Bayer Leverkusen": "勒沃库森", "Eintracht Frankfurt": "法兰克福", "法兰克福": "法兰克福",
    "Borussia Monchengladbach": "门兴格拉德巴赫", "VfB Stuttgart": "斯图加特",
    "Werder Bremen": "云达不来梅", "SC Freiburg": "弗赖堡", "1899 Hoffenheim": "霍芬海姆",
    "TSG Hoffenheim": "霍芬海姆", "VfL Wolfsburg": "沃尔夫斯堡", "Union Berlin": "柏林联合",
    "FSV Mainz 05": "美因茨", "Schalke 04": "沙尔克04", "SV Elversberg": "埃尔弗斯贝格",
    "SC Paderborn 07": "帕德博恩", "1. FC Koln": "科隆", "FC Cologne": "科隆",
    "Hamburger SV": "汉堡", "Hertha Berlin": "柏林赫塔", "FC Augsburg": "奥格斯堡",
    # 法甲
    "Paris Saint-Germain": "巴黎圣日耳曼", "Marseille": "马赛", "Olympique de Marseille": "马赛",
    "AS Monaco": "摩纳哥", "Monaco": "摩纳哥", "Lille": "里尔", "Lyon": "里昂", "Nice": "尼斯",
    "Lens": "朗斯", "Stade Rennais": "雷恩", "Rennes": "雷恩", "Stade Brest": "布雷斯特",
    "Brest": "布雷斯特", "AJ Auxerre": "欧塞尔", "Auxerre": "欧塞尔", "Nantes": "南特",
    "RC Strasbourg": "斯特拉斯堡", "Strasbourg": "斯特拉斯堡", "Toulouse": "图卢兹",
    "Montpellier": "蒙彼利埃", "Le Havre": "勒阿弗尔", "Angers": "昂热", "Reims": "兰斯",
}

STATUS_MAP = {
    "STATUS_SCHEDULED": ("scheduled", None),
    "STATUS_FINAL": ("finished", 90),
    "STATUS_FULL_TIME": ("finished", 90),
    "STATUS_IN_PROGRESS": ("live", None),
    "STATUS_HALFTIME": ("halftime", 45),
    "STATUS_END_PERIOD": ("halftime", 45),
    "STATUS_POSTPONED": ("scheduled", None),
    "STATUS_DELAYED": ("scheduled", None),
    "STATUS_CANCELED": ("finished", None),
}


def _get(url: str, timeout: int = 12) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def _season_label(season: Any) -> str | None:
    """ESPN 的 season 结构不稳定（type 可能是 int），取年份作为赛季名。"""
    if not isinstance(season, dict):
        return None
    yr = season.get("year")
    typ = season.get("type")
    name = typ.get("name") if isinstance(typ, dict) else None
    if name:
        return str(name)
    return f"{yr}/{str(int(yr) + 1)[-2:]}" if isinstance(yr, int) else None


def _minute(clock: str | None, fallback_state: str | None = None) -> int | None:
    """'57'' -> 57 ; \"45'+2'\" -> 45."""
    if not clock:
        return None
    m = re.search(r"(\d+)", clock)
    if not m:
        return None
    return int(m.group(1))


def fetch_scoreboard(slug: str) -> list[dict[str, Any]]:
    """拉取某联赛最近一轮/今日赛程（ESPN 无日期参数时返回最近赛程）。"""
    d = _get(f"{BASE}/{slug}/scoreboard")
    out: list[dict[str, Any]] = []
    for e in d.get("events", []):
        comp = (e.get("competitions") or [{}])[0]
        comps = comp.get("competitors") or []
        if len(comps) != 2:
            continue
        home = next((c for c in comps if c.get("homeAway") == "home"), comps[0])
        away = next((c for c in comps if c.get("homeAway") == "away"), comps[1])
        st_type = (comp.get("status") or {}).get("type") or {}
        name = st_type.get("name") or ""
        state = st_type.get("state") or ""
        status, minute = STATUS_MAP.get(name, (None, None))
        if status is None:
            status = {"pre": "scheduled", "in": "live", "post": "finished"}.get(state, "scheduled")
        if minute is None:
            minute = _minute((comp.get("status") or {}).get("displayClock"))
        if status == "scheduled":
            minute = None
        out.append({
            "event_id": str(e.get("id")),
            "slug": slug,
            "kickoff": e.get("date"),
            "home": {
                "id": str((home.get("team") or {}).get("id")),
                "name": (home.get("team") or {}).get("displayName"),
                "short": (home.get("team") or {}).get("shortDisplayName"),
                "abbr": (home.get("team") or {}).get("abbreviation"),
                "color": (home.get("team") or {}).get("color"),
            },
            "away": {
                "id": str((away.get("team") or {}).get("id")),
                "name": (away.get("team") or {}).get("displayName"),
                "short": (away.get("team") or {}).get("shortDisplayName"),
                "abbr": (away.get("team") or {}).get("abbreviation"),
                "color": (away.get("team") or {}).get("color"),
            },
            "status": status,
            "minute": minute,
            "score_home": _to_int(home.get("score")),
            "score_away": _to_int(away.get("score")),
            "venue": ((comp.get("venue") or {}) if isinstance(comp.get("venue"), dict) else {}).get("fullName"),
            "round": _season_label(e.get("season")),
        })
    return out


def _to_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def fetch_summary(slug: str, event_id: str) -> dict[str, Any]:
    """比赛详情：关键事件 + boxscore 技术统计。"""
    d = _get(f"{BASE}/{slug}/summary?event={event_id}", timeout=15)
    events: list[dict[str, Any]] = []
    for e in d.get("keyEvents", []) or []:
        etype = ((e.get("type") or {}).get("text") or "").lower()
        minute = _minute((e.get("clock") or {}).get("displayValue")) or 0
        side = None
        team_id = str((e.get("team") or {}).get("id") or "")
        if "goal" in etype and "disallow" not in etype and "own" not in etype:
            kind = "goal"
        elif "yellow" in etype:
            kind = "yellow_card"
        elif "red" in etype:
            kind = "red_card"
        elif "substitut" in etype:
            kind = "substitution"
        elif "penalty" in etype and "miss" not in etype:
            kind = "goal"
        else:
            continue
        athletes = e.get("athletesInvolved") or []
        player = athletes[0].get("displayName") if athletes else None
        related = athletes[1].get("displayName") if len(athletes) > 1 else None
        if player is None and e.get("text"):
            # 文本兜底："Goal! ... Alexander Isak (Liverpool) ..."
            m = re.search(r"\.\s*([A-Z][\w\'\-\. ]+)\s*\(", e["text"])
            player = m.group(1).strip() if m else None
        events.append({
            "minute": minute, "type": kind, "team_id": team_id,
            "player": player, "related": related, "detail": e.get("text"),
        })
    stats: dict[str, Any] = {}
    for t in (d.get("boxscore") or {}).get("teams", []) or []:
        vals = {s.get("name"): s.get("displayValue") for s in t.get("statistics", []) or []}
        stats[str((t.get("team") or {}).get("id"))] = vals
    return {"events": events, "stats": stats, "raw": d}


# ---------------- 同步（写入本地库） ----------------

def _norm(name: str | None) -> str:
    s = (name or "").lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\b(fc|cf|afc|sc|sv|as|ss|ac|real|club|de|the)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _resolve_team(db: Session, info: dict[str, Any], league_id: int, league_cn: str):
    """ESPN 球队 -> 本地 Team（先查中文别名/英文名，缺失则建真实球队）。"""
    from app.models import Team, TeamRating

    name = info.get("name") or "Unknown"
    # 1) provider_team_id 命中
    t = db.query(Team).filter(Team.provider_team_id == info.get("id")).first()
    if t:
        return t
    # 2) 中文别名对应的英文名 / name_en 归一化匹配
    cn = TEAM_CN.get(name)
    if cn:
        t = db.query(Team).filter(Team.name == cn).first()
        if t:
            t.provider = "espn"
            t.provider_team_id = info.get("id")
            db.flush()
            return t
    target = _norm(name)
    for cand in db.query(Team).all():
        if _norm(cand.name_en) == target or _norm(cand.name) == target:
            cand.provider = "espn"
            cand.provider_team_id = info.get("id")
            db.flush()
            return cand
    # 3) 新建真实球队（默认 Elo/TPI，避免污染模拟球队的评级）
    short = (info.get("abbr") or info.get("short") or name)[:4]
    t = Team(
        league_id=league_id, name=cn or name, name_en=name,
        short_name=short.upper(), country=league_cn,
        color=f"#{(info.get('color') or '333333').lstrip('#')}"[:7],
        elo_rating=1500.0, stadium=info.get("venue") or f"{name}球场",
        provider="espn", provider_team_id=info.get("id"),
    )
    db.add(t)
    db.flush()
    db.add(TeamRating(
        team_id=t.id, tpi=50.0, attack=50.0, defense=50.0, form=50.0,
        possession=50.0, pressing=50.0, efficiency=50.0,
        breakdown={"form_last10": [], "season": {}, "source": "espn"},
    ))
    db.flush()
    return t


def _resolve_league(db: Session, slug: str):
    from app.models import League, Season

    cn, en, short = LEAGUES[slug]
    lg = db.query(League).filter(League.name == cn).first()
    if not lg:
        lg = League(name=cn, name_en=en, short_name=short, country=en)
        db.add(lg)
        db.flush()
        db.add(Season(league_id=lg.id, name="2026/27", is_current=True))
        db.flush()
    return lg


def _upsert_prediction(db: Session, m, home_elo: float, away_elo: float) -> None:
    from app.core.predictor import prematch
    from app.models import MatchPrediction

    pred = prematch(home_elo, away_elo)
    try:
        from app.ml.train import blend, predict_proba

        ml = predict_proba(home_elo - away_elo, 0.5, 0.5)
        pred = blend(pred, ml)
    except Exception:
        pred["model_version"] = "dc-only-v0.1"
    row = m.prediction
    if row is None:
        row = MatchPrediction(match_id=m.id, **pred)
        db.add(row)
    else:
        for k, v in pred.items():
            setattr(row, k, v)


def _stats_payload(stats: dict[str, Any], home_id: str, away_id: str) -> dict[str, Any] | None:
    h = stats.get(home_id) or {}
    a = stats.get(away_id) or {}
    if not h and not a:
        return None

    def g(d: dict, key: str, default: float = 0.0) -> float:
        try:
            return float(d.get(key, default))
        except (TypeError, ValueError):
            return default

    return {
        "minute": 90,
        "possession_home": round(g(h, "possessionPct", 50.0)),
        "shots_home": int(g(h, "totalShots")), "shots_away": int(g(a, "totalShots")),
        "shots_on_target_home": int(g(h, "shotsOnTarget")),
        "shots_on_target_away": int(g(a, "shotsOnTarget")),
        "corners_home": int(g(h, "wonCorners")), "corners_away": int(g(a, "wonCorners")),
        "fouls_home": int(g(h, "foulsCommitted")), "fouls_away": int(g(a, "foulsCommitted")),
        "yellow_home": int(g(h, "yellowCards")), "yellow_away": int(g(a, "yellowCards")),
        "red_home": int(g(h, "redCards")), "red_away": int(g(a, "redCards")),
        "dangerous_home": int(g(h, "totalShots") * 4), "dangerous_away": int(g(a, "totalShots") * 4),
        "xg_home": round(g(h, "totalShots") * 0.11, 2),
        "xg_away": round(g(a, "totalShots") * 0.11, 2),
    }


_last_sync: dict[str, Any] = {"ok": None, "at": None, "matches": 0, "error": None}


def last_sync() -> dict[str, Any]:
    return dict(_last_sync)


def sync(db: Session, with_details: bool = True, keep_days: int = 14) -> dict[str, Any]:
    """同步真实赛程/比分/统计到本地库。返回同步摘要。"""
    from app.models import Match, MatchEvent, Player

    result = {"ok": False, "leagues": 0, "matches": 0, "live": 0, "events": 0, "error": None}
    try:
        now = datetime.now(timezone.utc)
        seen_ids: set[int] = set()
        for slug in LEAGUES:
            try:
                rows = fetch_scoreboard(slug)
            except Exception as e:
                result["error"] = f"{slug}: {e}"
                continue
            result["leagues"] += 1
            lg = _resolve_league(db, slug)
            for r in rows:
                home = _resolve_team(db, r["home"], lg.id, lg.name)
                away = _resolve_team(db, r["away"], lg.id, lg.name)
                m = db.query(Match).filter(
                    Match.provider == "espn", Match.provider_event_id == r["event_id"]
                ).first()
                if m is None:
                    m = Match(
                        league_id=lg.id, home_team_id=home.id, away_team_id=away.id,
                        kickoff_at=_parse_dt(r["kickoff"]) or now,
                        venue=r.get("venue"), round=r.get("round"),
                        sim_seed=0, provider="espn", provider_event_id=r["event_id"],
                    )
                    db.add(m)
                    db.flush()
                m.kickoff_at = _parse_dt(r["kickoff"]) or m.kickoff_at
                m.home_team_id, m.away_team_id = home.id, away.id
                m.status_override = r["status"]
                m.minute_override = r["minute"]
                m.score_home = r["score_home"]
                m.score_away = r["score_away"]
                m.stats_json = None
                seen_ids.add(m.id)
                result["matches"] += 1
                if r["status"] in ("live", "halftime"):
                    result["live"] += 1
                _upsert_prediction(db, m, home.elo_rating, away.elo_rating)
                db.flush()

                # 详情（事件/统计/阵容）——已完赛或进行中的比赛才需要
                if with_details and r["status"] in ("finished", "live", "halftime"):
                    try:
                        s = fetch_summary(slug, r["event_id"])
                    except Exception:
                        s = None
                    if s:
                        m.stats_json = _stats_payload(
                            s["stats"], str(r["home"]["id"]), str(r["away"]["id"]))
                        # 真实阵容（一次即可，后续靠队内姓名去重）
                        for grp in (s["raw"].get("rosters") or []):
                            side = grp.get("homeAway")
                            entries = grp.get("roster") or []
                            if isinstance(entries, list) and entries:
                                _sync_roster(
                                    db, home if side == "home" else away, entries, side)
                        # 事件：同 provider_event_id 幂等重建
                        db.query(MatchEvent).filter(MatchEvent.match_id == m.id).delete()
                        id_home, id_away = str(r["home"]["id"]), str(r["away"]["id"])
                        for ev in s["events"]:
                            side = None
                            if ev["team_id"] == id_home:
                                side = "home"
                            elif ev["team_id"] == id_away:
                                side = "away"
                            if side is None:
                                continue
                            pid = _find_or_create_player(db, ev["player"], home if side == "home" else away)
                            rid = _find_or_create_player(db, ev["related"], home if side == "home" else away)
                            db.add(MatchEvent(
                                match_id=m.id, minute=ev["minute"], side=side,
                                type=ev["type"], player_id=pid, related_player_id=rid,
                                detail=(ev.get("detail") or "")[:180] or None,
                            ))
                            result["events"] += 1
                        db.flush()
        # 清理：模拟比赛 + 过期的真实比赛（超出保留窗口且非今日）
        if result["matches"]:
            db.query(Match).filter(Match.provider != "espn").delete(synchronize_session=False)
            cutoff = now - timedelta(days=keep_days)
            old = db.query(Match).filter(
                Match.provider == "espn",
                Match.kickoff_at < cutoff,
            ).all()
            for m in old:
                db.query(MatchEvent).filter(MatchEvent.match_id == m.id).delete()
                db.delete(m)
        db.commit()
        result["ok"] = bool(result["matches"])
        _last_sync.update({
            "ok": result["ok"], "at": now.isoformat(),
            "matches": result["matches"], "error": result["error"],
        })
    except Exception as e:  # 同步失败不影响服务
        db.rollback()
        result["error"] = str(e)
        _last_sync.update({"ok": False, "at": datetime.now(timezone.utc).isoformat(),
                           "error": str(e)})
    return result


def _find_or_create_player(db: Session, name: str | None, team) -> int | None:
    """真实球员：按队内姓名匹配，缺失则建占位球员（真实数据源无赛季汇总数据）。"""
    from app.models import Player

    if not name:
        return None
    p = db.query(Player).filter(Player.team_id == team.id, Player.name_en == name).first()
    if p:
        return p.id
    p = Player(
        team_id=team.id, name=name, name_en=name, position="MF",
        number=0, age=0, rating=6.5, ai_rating=6.5, status="normal",
        season_stats={}, provider="espn",
    )
    db.add(p)
    db.flush()
    return p.id


_POS_MAP = {"G": "GK", "GK": "GK", "D": "DF", "DF": "DF", "M": "MF", "MF": "MF",
            "F": "FW", "FW": "FW", "A": "FW", "ST": "FW"}


def _sync_roster(db: Session, team, roster: list, home_away: str) -> int:
    """把 ESPN 阵容写入球队（真实球员：姓名/号码/位置）。"""
    from app.models import Player

    created = 0
    for entry in roster or []:
        ath = entry.get("athlete") or {}
        name = ath.get("displayName") or ath.get("shortName")
        if not name:
            continue
        pos_raw = entry.get("position") or ath.get("position") or {}
        if isinstance(pos_raw, dict):
            pos_raw = pos_raw.get("abbreviation") or ""
        jersey = entry.get("jersey") or ath.get("jersey")
        try:
            jersey = int(jersey) if jersey else 0
        except (TypeError, ValueError):
            jersey = 0
        exists = db.query(Player).filter(
            Player.team_id == team.id, Player.name_en == name).first()
        if exists:
            if exists.provider != "espn":
                exists.provider = "espn"
            if jersey and exists.number == 0:
                exists.number = jersey
            continue
        db.add(Player(
            team_id=team.id, name=name, name_en=name,
            position=_POS_MAP.get(str(pos_raw).upper(), "MF"),
            number=jersey, age=ath.get("age") or 0,
            rating=6.5, ai_rating=6.5, status="normal",
            season_stats={}, provider="espn",
        ))
        created += 1
    db.flush()
    return created


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
