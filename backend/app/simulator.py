"""模拟数据引擎（Phase 2 数据源）。

设计要点：
- 确定性模拟：每场比赛一个 sim_seed，事件/统计可重放、可复现
- 状态惰性推导：比赛状态(分钟/比分/统计)是 kickoff 时间的函数，API 无状态、重启安全
- 事件在种子阶段一次性生成入库，实时可见性按当前分钟过滤
"""
import math
import random
from datetime import date, datetime, timedelta, timezone

import numpy as np
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.predictor import prematch
from app.models import (
    League,
    Match,
    MatchEvent,
    MatchPrediction,
    Player,
    Season,
    Team,
)

UTC = timezone.utc

# ---------------- 静态数据（真实联赛/球队观感，Elo 为示意值） ----------------
LEAGUES: dict[str, dict] = {
    "Premier League": {
        "short": "EPL", "country": "England",
        "teams": [
            ("Liverpool", "LIV", "#c8102e", 1943), ("Manchester City", "MCI", "#6cabdd", 1978),
            ("Arsenal", "ARS", "#ef0107", 1952), ("Chelsea", "CHE", "#034694", 1878),
            ("Manchester United", "MUN", "#da291c", 1815), ("Tottenham", "TOT", "#132257", 1795),
            ("Newcastle", "NEW", "#4d4d4d", 1822), ("Aston Villa", "AVL", "#95bfe8", 1801),
            ("West Ham", "WHU", "#7a263a", 1725), ("Brighton", "BHA", "#0057b8", 1748),
            ("Everton", "EVE", "#003399", 1690), ("Wolves", "WOL", "#fdb913", 1672),
        ],
    },
    "La Liga": {
        "short": "LAL", "country": "Spain",
        "teams": [
            ("Real Madrid", "RMA", "#febe10", 1990), ("Barcelona", "BAR", "#a50044", 1955),
            ("Atletico Madrid", "ATM", "#cb3524", 1880), ("Athletic Club", "ATH", "#ee2523", 1800),
            ("Villarreal", "VIL", "#ffe667", 1770), ("Real Betis", "BET", "#00954c", 1745),
            ("Valencia", "VAL", "#ee8707", 1720), ("Sevilla", "SEV", "#d91a21", 1735),
            ("Real Sociedad", "RSO", "#0067b1", 1760), ("Girona", "GIR", "#d6001c", 1785),
            ("Celta Vigo", "CEL", "#8ac3ee", 1690), ("Osasuna", "OSA", "#d91a21", 1685),
        ],
    },
    "Serie A": {
        "short": "SEA", "country": "Italy",
        "teams": [
            ("Inter", "INT", "#0068a8", 1925), ("AC Milan", "MIL", "#fb090b", 1855),
            ("Juventus", "JUV", "#003c82", 1860), ("Napoli", "NAP", "#12a0d7", 1845),
            ("Roma", "ROM", "#8e1f2f", 1800), ("Lazio", "LAZ", "#87d8f7", 1790),
            ("Atalanta", "ATA", "#1c1c1c", 1830), ("Fiorentina", "FIO", "#592c82", 1775),
            ("Bologna", "BOL", "#a21c25", 1760), ("Torino", "TOR", "#8a1538", 1720),
            ("Udinese", "UDI", "#1b1b1b", 1700), ("Genoa", "GEN", "#b4132a", 1685),
        ],
    },
    "Bundesliga": {
        "short": "SEA-D", "country": "Germany",
        "teams": [
            ("Bayern Munich", "BAY", "#dc052d", 1955), ("Leverkusen", "B04", "#e32221", 1890),
            ("Dortmund", "BVB", "#fde100", 1865), ("RB Leipzig", "RBL", "#dd0741", 1830),
            ("Stuttgart", "VFB", "#e32219", 1800), ("Frankfurt", "SGE", "#e1000f", 1780),
            ("Freiburg", "SCF", "#e2001a", 1735), ("Hoffenheim", "TSG", "#1c63b7", 1710),
            ("Wolfsburg", "WOB", "#65b32e", 1725), ("Union Berlin", "FCU", "#eb1923", 1700),
            ("Werder Bremen", "SVW", "#1d9053", 1695), ("Gladbach", "BMG", "#00a650", 1705),
        ],
    },
    "Ligue 1": {
        "short": "FL1", "country": "France",
        "teams": [
            ("Paris Saint-Germain", "PSG", "#004170", 1975), ("Monaco", "ASM", "#e63312", 1810),
            ("Marseille", "OM", "#2faee0", 1795), ("Lille", "LIL", "#e01e13", 1780),
            ("Lyon", "OL", "#1b1f63", 1765), ("Nice", "NIC", "#c8102e", 1755),
            ("Lens", "RCL", "#fff200", 1770), ("Rennes", "SRFC", "#e23328", 1730),
        ],
    },
}

NAME_POOLS: dict[str, list[str]] = {
    "England": ["Smith", "Walker", "Barnes", "Hughes", "Turner", "Clarke", "Wright", "Foster",
                "Palmer", "Gordon", "Reed", "Chambers", "Doyle", "Ellis", "Grant", "Hart",
                "Murray", "Shaw", "West", "Baker", "Cole", "Mason", "Dawson", "Henderson"],
    "Spain": ["Garcia", "Martinez", "Lopez", "Sanchez", "Fernandez", "Torres", "Ruiz", "Navas",
              "Moreno", "Ortega", "Iglesias", "Cabrera", "Vidal", "Serrano", "Ramos", "Molina",
              "Castro", "Ortiz", "Delgado", "Vargas", "Alonso", "Dominguez", "Pascual", "Prieto"],
    "Italy": ["Rossi", "Ferrari", "Russo", "Bianchi", "Romano", "Gallo", "Costa", "Fontana",
              "Conti", "Ricci", "Marino", "Greco", "Bruno", "Serra", "Mancini", "Longo",
              "Barbieri", "Moretti", "Rinaldi", "Caruso", "Ferrara", "Gatti", "Leone", "Marchi"],
    "Germany": ["Muller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker",
                "Hoffmann", "Koch", "Richter", "Klein", "Braun", "Lehmann", "Krause", "Vogel",
                "Lang", "Stein", "Franke", "Berger", "Winkler", "Busch", "Sommer", "Fritz"],
    "France": ["Martin", "Bernard", "Dubois", "Thomas", "Robert", "Richard", "Petit", "Durand",
               "Leroy", "Moreau", "Simon", "Laurent", "Michel", "Garnier", "Faure", "Rousseau",
               "Blanc", "Guerin", "Boyer", "Girard", "Bonnet", "Dupont", "Lambert", "Fontaine"],
}

GOAL_DETAILS = ["禁区内推射", "左脚远射世界波", "头球破门", "单刀冷静推射", "点球命中",
                "禁区混战补射", "任意球直接得分", "反击低射远角"]
ASSIST_DETAILS = ["下底传中助攻", "直塞撕开防线", "角球助攻", "远射中框补射", "反抢后横传"]


# ---------------- 比赛状态推导（kickoff 时间的函数） ----------------
def match_state(kickoff: datetime, now: datetime | None = None) -> dict:
    """比赛状态惰性推导：scheduled / live(1H) / halftime / live(2H) / finished。"""
    now = now or datetime.now(UTC)
    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=UTC)
    elapsed = (now - kickoff).total_seconds() / 60.0
    if elapsed < 0:
        return {"status": "scheduled", "period": None, "minute": None}
    if elapsed < settings.HALF_MINUTES:
        return {"status": "live", "period": "1H", "minute": int(elapsed) + 1}
    if elapsed < settings.HALF_MINUTES + settings.HALFTIME_BREAK:
        return {"status": "halftime", "period": "HT", "minute": 45}
    if elapsed < settings.HALF_MINUTES * 2 + settings.HALFTIME_BREAK:
        return {"status": "live", "period": "2H",
                "minute": min(int(elapsed) - settings.HALFTIME_BREAK, 90)}
    return {"status": "finished", "period": "FT", "minute": 90}


# ---------------- 事件与统计生成 ----------------
def _pick_scorer(rng: random.Random, players: list[Player]) -> Player:
    weights = [{"GK": 0.1, "DF": 1.2, "MF": 3.0, "FW": 5.5}[p.position] for p in players]
    return rng.choices(players, weights=weights, k=1)[0]


def _gen_events_for_team(
    rng: random.Random, side: str, lam: float, squad: list[Player], offset: float
) -> list[dict]:
    events: list[dict] = []
    # 进球：泊松分布 + 位置三角分布（下半场略多）
    n_goals = min(rng.choices(
        range(0, 6), weights=[_w(lam, k) for k in range(6)], k=1)[0], 5)
    for _ in range(n_goals):
        minute = int(rng.triangular(4, 92, 58))
        scorer = _pick_scorer(rng, squad)
        events.append({
            "minute": minute, "side": side, "type": "goal",
            "player_id": scorer.id, "detail": rng.choice(GOAL_DETAILS),
            "x": round(offset + rng.uniform(0.02, 0.16), 3),
            "y": round(rng.uniform(0.2, 0.8), 3),
        })
    # 黄牌 2-5 张 / 红牌 6% 概率 1 张
    for _ in range(rng.randint(2, 5)):
        events.append({
            "minute": int(rng.triangular(10, 92, 62)), "side": side,
            "type": "yellow_card", "player_id": rng.choice(squad).id,
            "detail": "战术犯规", "x": None, "y": None,
        })
    if rng.random() < 0.06:
        events.append({
            "minute": int(rng.triangular(50, 88, 75)), "side": side,
            "type": "red_card", "player_id": rng.choice(squad).id,
            "detail": "两黄变一红" if rng.random() < 0.5 else "直接红牌",
            "x": None, "y": None,
        })
    # 换人 2-3 个（46-85 分钟）
    outfield = [p for p in squad if p.position != "GK"]
    outs = rng.sample(outfield, k=min(3, len(outfield)))
    for i, out_p in enumerate(outs[: rng.randint(2, 3)]):
        ins = [p for p in outfield if p.id != out_p.id and p.position == out_p.position]
        events.append({
            "minute": rng.randint(46, 85), "side": side, "type": "substitution",
            "player_id": rng.choice(ins).id if ins else rng.choice(outfield).id,
            "related_player_id": out_p.id, "detail": "战术换人",
            "x": None, "y": None,
        })
    return events


def _w(lam: float, k: int) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def generate_events(rng: random.Random, match: Match, squads: dict[str, list[Player]],
                    lam_h: float, lam_a: float) -> list[MatchEvent]:
    raw = (_gen_events_for_team(rng, "home", lam_h, squads["home"], 0.78)
           + _gen_events_for_team(rng, "away", lam_a, squads["away"], 0.06))
    raw.sort(key=lambda e: e["minute"])
    return [MatchEvent(match_id=match.id, **e) for e in raw]


def stats_series(seed: int, minute: int, lam_h: float, lam_a: float,
                 elo_diff: float, goal_minutes_home: list[int],
                 goal_minutes_away: list[int]) -> list[dict]:
    """分钟级统计序列（确定性）。minute <=0 返回空。"""
    if minute <= 0:
        return []
    rs = np.random.RandomState(seed)
    mins = np.arange(1, minute + 1)
    n = len(mins)
    # 强度系数：Elo 差决定攻防倾向
    s_h = 1 + elo_diff / 800.0
    s_a = 1 - elo_diff / 800.0
    shots_h = rs.poisson(0.145 * s_h, n)
    shots_a = rs.poisson(0.145 * s_a, n)
    on_h = rs.binomial(shots_h, 0.38)  # 射正：每次射门 38% 概率
    on_a = rs.binomial(shots_a, 0.38)
    corners_h = rs.poisson(0.10 * s_h, n)
    corners_a = rs.poisson(0.10 * s_a, n)
    fouls_h = rs.poisson(0.11, n)
    fouls_a = rs.poisson(0.11, n)
    da_h = rs.poisson(0.55 * s_h, n)
    da_a = rs.poisson(0.55 * s_a, n)
    base_pos = 50 + int(np.clip(elo_diff / 12.0, -14, 14))
    pos_noise = np.clip(rs.normal(0, 4, n).cumsum() * 0.15, -8, 8)
    poss = np.clip(base_pos + pos_noise, 30, 70).round().astype(int)
    xg_h = (shots_h * 0.095 + rs.normal(0, 0.012, n)).clip(0)
    xg_a = (shots_a * 0.095 + rs.normal(0, 0.012, n)).clip(0)
    cum = lambda arr: np.cumsum(arr)
    gh, ga = np.zeros(n, int), np.zeros(n, int)
    for m in goal_minutes_home:
        gh[mins <= m] += 1
    for m in goal_minutes_away:
        ga[mins <= m] += 1
    # xG 不低于实际进球的折扣值（保证合理性）
    xg_h_cum = np.maximum(cum(xg_h), gh * 0.45)
    xg_a_cum = np.maximum(cum(xg_a), ga * 0.45)
    series = []
    for i in range(n):
        series.append({
            "minute": int(mins[i]),
            "possession_home": int(poss[i]),
            "shots_home": int(cum(shots_h)[i]), "shots_away": int(cum(shots_a)[i]),
            "shots_on_target_home": max(int(cum(on_h)[i]), int(gh[i])),
            "shots_on_target_away": max(int(cum(on_a)[i]), int(ga[i])),
            "corners_home": int(cum(corners_h)[i]), "corners_away": int(cum(corners_a)[i]),
            "fouls_home": int(cum(fouls_h)[i]), "fouls_away": int(cum(fouls_a)[i]),
            "yellow_home": 0, "yellow_away": 0, "red_home": 0, "red_away": 0,
            "dangerous_home": int(cum(da_h)[i]), "dangerous_away": int(cum(da_a)[i]),
            "xg_home": round(float(xg_h_cum[i]), 2),
            "xg_away": round(float(xg_a_cum[i]), 2),
        })
    return series


# ---------------- 全量种子 ----------------
def seed_all(db: Session, force: bool = False) -> bool:
    """建库种子：5 联赛 / 64 球队 / 球员 / 近 3 日赛程 / 事件 / 赛前预测。
    返回是否执行了种子。"""
    if not force and db.query(Match).count() > 0:
        return False

    now = datetime.now(UTC)
    today = date.today()
    rng_master = random.Random(20260927)

    # 球员名池索引
    name_cursor = {c: 0 for c in NAME_POOLS}

    for lg_name, lg in LEAGUES.items():
        league = League(name=lg_name, short_name=lg["short"], country=lg["country"])
        db.add(league)
        db.flush()
        season = Season(
            league_id=league.id, name="2026/27",
            start_date=date(today.year, 8, 1), end_date=date(today.year + 1, 5, 31),
            is_current=True,
        )
        db.add(season)

        teams: list[Team] = []
        for name, short, color, elo in lg["teams"]:
            t = Team(league_id=league.id, name=name, short_name=short,
                     country=lg["country"], color=color, elo_rating=float(elo),
                     stadium=f"{name} Arena")
            db.add(t)
            teams.append(t)
        db.flush()

        # 每队 18 名球员：2 GK / 6 DF / 6 MF / 4 FW
        squads: dict[int, list[Player]] = {}
        for ti, t in enumerate(teams):
            pool = NAME_POOLS[lg["country"]]
            players: list[Player] = []
            num = 1
            for pos, count in (("GK", 2), ("DF", 6), ("MF", 6), ("FW", 4)):
                for _ in range(count):
                    name_cursor[lg["country"]] = (
                        name_cursor[lg["country"]] + rng_master.randint(1, 3)
                    ) % len(pool)
                    players.append(Player(
                        team_id=t.id, name=pool[name_cursor[lg["country"]]],
                        position=pos, number=num,
                        age=rng_master.randint(20, 34),
                        rating=round(rng_master.uniform(6.2, 8.6), 1),
                    ))
                    num += 1
            db.add_all(players)
            squads[t.id] = players
        db.flush()

        # 赛程：昨日 3 场完赛 + 今日 7 场（2 完赛 / 3 进行中 / 2 未开始）+ 明日 3 场
        # 用时区感知的相对 kickoff，保证任何时候启动都有进行中的比赛
        schedule: list[tuple[float, str]] = [
            (-140, "finished"), (-150, "finished"), (-160, "finished"),
            (-30, "live"), (-68, "live"), (-55, "live"),
            (+40, "scheduled"), (+150, "scheduled"),
        ]
        pool_teams = teams[:]
        rng_master.shuffle(pool_teams)
        pair_i = 0
        match_no = 0
        for offset, _tag in schedule:
            home = pool_teams[pair_i % len(pool_teams)]
            away = pool_teams[(pair_i + 1) % len(pool_teams)]
            pair_i += 2
            match_no += 1
            m = Match(
                league_id=league.id, home_team_id=home.id, away_team_id=away.id,
                kickoff_at=now + timedelta(minutes=offset),
                venue=home.stadium, round=f"Regular Season - {6 + match_no % 3}",
                sim_seed=rng_master.randint(1, 10**9),
            )
            db.add(m)
            db.flush()

            pred = prematch(home.elo_rating, away.elo_rating)
            db.add(MatchPrediction(match_id=m.id, **pred))

            m_events = generate_events(
                random.Random(m.sim_seed), m,
                {"home": squads[home.id], "away": squads[away.id]},
                pred["lambda_home"], pred["lambda_away"],
            )
            db.add_all(m_events)
        db.flush()
    db.commit()
    return True
