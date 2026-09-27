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
    TeamRating,
)

UTC = timezone.utc

# ---------------- 静态数据（真实联赛/球队观感，Elo 为示意值；中文名用于全站展示） ----------------
LEAGUES: dict[str, dict] = {
    "英超": {
        "name_en": "Premier League", "short": "英超", "country": "England",
        "teams": [
            ("利物浦", "Liverpool", "LIV", "#c8102e", 1943), ("曼城", "Manchester City", "MCI", "#6cabdd", 1978),
            ("阿森纳", "Arsenal", "ARS", "#ef0107", 1952), ("切尔西", "Chelsea", "CHE", "#034694", 1878),
            ("曼联", "Manchester United", "MUN", "#da291c", 1815), ("热刺", "Tottenham", "TOT", "#132257", 1795),
            ("纽卡斯尔", "Newcastle", "NEW", "#4d4d4d", 1822), ("阿斯顿维拉", "Aston Villa", "AVL", "#95bfe8", 1801),
            ("西汉姆联", "West Ham", "WHU", "#7a263a", 1725), ("布莱顿", "Brighton", "BHA", "#0057b8", 1748),
            ("埃弗顿", "Everton", "EVE", "#003399", 1690), ("狼队", "Wolves", "WOL", "#fdb913", 1672),
        ],
    },
    "西甲": {
        "name_en": "La Liga", "short": "西甲", "country": "Spain",
        "teams": [
            ("皇家马德里", "Real Madrid", "RMA", "#febe10", 1990), ("巴塞罗那", "Barcelona", "BAR", "#a50044", 1955),
            ("马德里竞技", "Atletico Madrid", "ATM", "#cb3524", 1880), ("毕尔巴鄂竞技", "Athletic Club", "ATH", "#ee2523", 1800),
            ("比利亚雷亚尔", "Villarreal", "VIL", "#ffe667", 1770), ("皇家贝蒂斯", "Real Betis", "BET", "#00954c", 1745),
            ("瓦伦西亚", "Valencia", "VAL", "#ee8707", 1720), ("塞维利亚", "Sevilla", "SEV", "#d91a21", 1735),
            ("皇家社会", "Real Sociedad", "RSO", "#0067b1", 1760), ("赫罗纳", "Girona", "GIR", "#d6001c", 1785),
            ("塞尔塔", "Celta Vigo", "CEL", "#8ac3ee", 1690), ("奥萨苏纳", "Osasuna", "OSA", "#d91a21", 1685),
        ],
    },
    "意甲": {
        "name_en": "Serie A", "short": "意甲", "country": "Italy",
        "teams": [
            ("国际米兰", "Inter", "INT", "#0068a8", 1925), ("AC米兰", "AC Milan", "MIL", "#fb090b", 1855),
            ("尤文图斯", "Juventus", "JUV", "#003c82", 1860), ("那不勒斯", "Napoli", "NAP", "#12a0d7", 1845),
            ("罗马", "Roma", "ROM", "#8e1f2f", 1800), ("拉齐奥", "Lazio", "LAZ", "#87d8f7", 1790),
            ("亚特兰大", "Atalanta", "ATA", "#1c1c1c", 1830), ("佛罗伦萨", "Fiorentina", "FIO", "#592c82", 1775),
            ("博洛尼亚", "Bologna", "BOL", "#a21c25", 1760), ("都灵", "Torino", "TOR", "#8a1538", 1720),
            ("乌迪内斯", "Udinese", "UDI", "#1b1b1b", 1700), ("热那亚", "Genoa", "GEN", "#b4132a", 1685),
        ],
    },
    "德甲": {
        "name_en": "Bundesliga", "short": "德甲", "country": "Germany",
        "teams": [
            ("拜仁慕尼黑", "Bayern Munich", "BAY", "#dc052d", 1955), ("勒沃库森", "Leverkusen", "B04", "#e32221", 1890),
            ("多特蒙德", "Dortmund", "BVB", "#fde100", 1865), ("莱比锡红牛", "RB Leipzig", "RBL", "#dd0741", 1830),
            ("斯图加特", "Stuttgart", "VFB", "#e32219", 1800), ("法兰克福", "Frankfurt", "SGE", "#e1000f", 1780),
            ("弗赖堡", "Freiburg", "SCF", "#e2001a", 1735), ("霍芬海姆", "Hoffenheim", "TSG", "#1c63b7", 1710),
            ("沃尔夫斯堡", "Wolfsburg", "WOB", "#65b32e", 1725), ("柏林联合", "Union Berlin", "FCU", "#eb1923", 1700),
            ("云达不来梅", "Werder Bremen", "SVW", "#1d9053", 1695), ("门兴格拉德巴赫", "Gladbach", "BMG", "#00a650", 1705),
        ],
    },
    "法甲": {
        "name_en": "Ligue 1", "short": "法甲", "country": "France",
        "teams": [
            ("巴黎圣日耳曼", "Paris Saint-Germain", "PSG", "#004170", 1975), ("摩纳哥", "Monaco", "ASM", "#e63312", 1810),
            ("马赛", "Marseille", "OM", "#2faee0", 1795), ("里尔", "Lille", "LIL", "#e01e13", 1780),
            ("里昂", "Lyon", "OL", "#1b1f63", 1765), ("尼斯", "Nice", "NIC", "#c8102e", 1755),
            ("朗斯", "Lens", "RCL", "#fff200", 1770), ("雷恩", "Rennes", "SRFC", "#e23328", 1730),
        ],
    },
}

NAME_POOLS: dict[str, list[str]] = {    "England": ["Smith", "Walker", "Barnes", "Hughes", "Turner", "Clarke", "Wright", "Foster",
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

# 中文译名池（与英文名池按索引对应生成）
NAME_POOLS_CN: dict[str, list[str]] = {
    "England": ["史密斯", "沃克", "巴恩斯", "休斯", "特纳", "克拉克", "赖特", "福斯特",
                "帕尔默", "戈登", "里德", "钱伯斯", "多伊尔", "埃利斯", "格兰特", "哈特",
                "默里", "肖", "韦斯特", "贝克", "科尔", "梅森", "道森", "亨德森"],
    "Spain": ["加西亚", "马丁内斯", "洛佩斯", "桑切斯", "费尔南德斯", "托雷斯", "鲁伊斯", "纳瓦斯",
              "莫雷诺", "奥尔特加", "伊格莱西亚斯", "卡布雷拉", "比达尔", "塞拉诺", "拉莫斯", "莫利纳",
              "卡斯特罗", "奥尔蒂斯", "德尔加多", "巴尔加斯", "阿隆索", "多明格斯", "帕斯夸尔", "普列托"],
    "Italy": ["罗西", "费拉里", "鲁索", "比安基", "罗马诺", "加洛", "科斯塔", "丰塔纳",
              "孔蒂", "里奇", "马里诺", "格雷科", "布鲁诺", "塞拉", "曼奇尼", "隆戈",
              "巴尔比耶里", "莫雷蒂", "里纳尔迪", "卡鲁索", "费拉拉", "加蒂", "莱昂内", "马尔基"],
    "Germany": ["穆勒", "施密特", "施耐德", "菲舍尔", "韦伯", "迈尔", "瓦格纳", "贝克尔",
                "霍夫曼", "科赫", "里希特", "克莱因", "布劳恩", "莱曼", "克劳泽", "福格尔",
                "朗格", "施泰因", "弗兰克", "贝尔格", "温克勒", "布施", "佐默", "弗里茨"],
    "France": ["马丁", "贝尔纳", "杜波依斯", "托马斯", "罗贝尔", "理查德", "珀蒂", "杜兰",
               "勒鲁瓦", "莫罗", "西蒙", "洛朗", "米歇尔", "加尔尼耶", "福尔", "卢梭",
               "布朗", "盖兰", "布瓦耶", "吉拉尔", "博内", "杜邦", "兰贝尔", "丰丹"],
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

    # 球员名池索引（中/英文池按同一游标推进，保证一一对应）
    name_cursor = {c: 0 for c in NAME_POOLS}

    for lg_name, lg in LEAGUES.items():
        league = League(name=lg_name, name_en=lg["name_en"],
                        short_name=lg["short"], country=lg["country"])
        db.add(league)
        db.flush()
        season = Season(
            league_id=league.id, name="2026/27",
            start_date=date(today.year, 8, 1), end_date=date(today.year + 1, 5, 31),
            is_current=True,
        )
        db.add(season)

        teams: list[Team] = []
        for name_cn, name_en, short, color, elo in lg["teams"]:
            t = Team(league_id=league.id, name=name_cn, name_en=name_en,
                     short_name=short, country=lg["country"], color=color,
                     elo_rating=float(elo), stadium=f"{name_cn}球场")
            db.add(t)
            teams.append(t)
        db.flush()

        # 每队 18 名球员：2 GK / 6 DF / 6 MF / 4 FW + 赛季汇总 + AI Rating
        squads: dict[int, list[Player]] = {}
        pos_rate = {"GK": 0.0, "DF": 0.06, "MF": 0.20, "FW": 0.48}   # 场均进球率
        assist_rate = {"GK": 0.0, "DF": 0.08, "MF": 0.22, "FW": 0.25}
        for t in teams:
            pool_en = NAME_POOLS[lg["country"]]
            pool_cn = NAME_POOLS_CN[lg["country"]]
            players: list[Player] = []
            num = 1
            for pos, count in (("GK", 2), ("DF", 6), ("MF", 6), ("FW", 4)):
                for _ in range(count):
                    name_cursor[lg["country"]] = (
                        name_cursor[lg["country"]] + rng_master.randint(1, 3)
                    ) % len(pool_en)
                    idx = name_cursor[lg["country"]]
                    matches_n = rng_master.randint(14, 22)
                    goals = int(np.random.poisson(pos_rate[pos] * matches_n))
                    assists = int(np.random.poisson(assist_rate[pos] * matches_n))
                    base = round(rng_master.uniform(6.2, 8.6), 1)
                    p = Player(
                        team_id=t.id,
                        name=pool_cn[idx], name_en=pool_en[idx],
                        position=pos, number=num,
                        age=rng_master.randint(20, 34),
                        rating=base,
                        status="normal",
                    )
                    # AI Player Rating：基础能力 + 赛季产出贡献，位置感知
                    contribution = goals * 0.55 + assists * 0.35
                    p.ai_rating = round(min(9.6, max(5.2, base * 0.72 + 5.8 * 0.28
                                                     + contribution * 0.06)), 1)
                    p.season_stats = {
                        "matches": matches_n, "goals": goals, "assists": assists,
                        "xg": round(goals * rng_master.uniform(0.82, 1.18), 2),
                        "xa": round(assists * rng_master.uniform(0.8, 1.2), 2),
                        "passes_per_match": round(rng_master.uniform(18, 62), 1),
                        "pass_accuracy": round(rng_master.uniform(72, 93), 1),
                        "tackles_per_match": round(
                            {"GK": 0.2, "DF": 2.4, "MF": 1.8, "FW": 0.6}[pos]
                            * rng_master.uniform(0.7, 1.3), 1),
                        "interceptions_per_match": round(
                            {"GK": 0.3, "DF": 1.6, "MF": 1.2, "FW": 0.4}[pos]
                            * rng_master.uniform(0.7, 1.3), 1),
                    }
                    players.append(p)
                    num += 1
            db.add_all(players)
            squads[t.id] = players
        db.flush()

        # Team Power Index：Elo 驱动 + 种子噪声，分项与近10场一并落库
        form_pct: dict[int, float] = {}
        for t in teams:
            r = random.Random(t.id * 7919)
            rel = (t.elo_rating - 1650) / 400.0        # 0~1 相对实力
            attack = round(min(96, max(38, 40 + rel * 50 + r.uniform(-6, 6))), 1)
            defense = round(min(96, max(38, 40 + rel * 50 + r.uniform(-6, 6))), 1)
            form = round(min(96, max(30, 40 + rel * 45 + r.uniform(-10, 10))), 1)
            possession = round(min(68, max(34, 46 + rel * 16 + r.uniform(-4, 4))), 1)
            pressing = round(min(95, max(40, 45 + rel * 35 + r.uniform(-8, 8))), 1)
            efficiency = round(min(95, max(35, 42 + rel * 40 + r.uniform(-8, 8))), 1)
            tpi = round(attack * 0.26 + defense * 0.26 + form * 0.18
                        + possession * 0.10 + pressing * 0.10 + efficiency * 0.10, 1)
            # 近10场：胜率随 form，W/D/L 序列
            p_win = form / 130.0
            form_list = []
            for _ in range(10):
                u = r.random()
                form_list.append("W" if u < p_win else ("D" if u < p_win + 0.26 else "L"))
            # 近期状态积分率（W=3 D=1），供预测模型作为特征
            form_pct[t.id] = round(
                sum(3 if f == "W" else 1 if f == "D" else 0 for f in form_list) / 30.0, 3)
            db.add(TeamRating(
                team_id=t.id, tpi=tpi, attack=attack, defense=defense,
                form=form, possession=possession, pressing=pressing,
                efficiency=efficiency,
                breakdown={
                    "form_last10": form_list,
                    "season": {
                        "matches": 20,
                        "wins": sum(1 for f in form_list if f == "W") * 2,
                        "goals_for": round(attack / 100 * 42 + r.uniform(-4, 4)),
                        "goals_against": round((100 - defense) / 100 * 38 + r.uniform(-4, 4)),
                        "xg": round(attack / 100 * 40, 1),
                        "xga": round((100 - defense) / 100 * 36, 1),
                    },
                },
            ))

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

            pred = prematch(home.elo_rating, away.elo_rating,
                            form_home=form_pct.get(home.id, 0.5),
                            form_away=form_pct.get(away.id, 0.5))
            # XGBoost 融合（logistic stacking），模型引擎见 ml/train.py
            try:
                from app.ml.train import blend, predict_proba

                ml = predict_proba(
                    home.elo_rating - away.elo_rating,
                    form_pct.get(home.id, 0.5), form_pct.get(away.id, 0.5),
                )
                pred = blend(pred, ml)
            except Exception as e:  # ML 不可用时保留纯 DC 基线
                pred["model_version"] = "dc-only-v0.1"
                print(f"[seed] ML blend skipped: {e}")
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


def ensure_upcoming_matches(db: Session) -> int:
    """滚动补赛：未完赛比赛不足时，按当前时间补一轮赛程。

    场次从种子阶段一次性生成，若程序连续运行数小时，全部比赛会踢完、
    平台进入"无实时比赛"的空窗。此函数在广播循环中周期调用：
    未完赛（kickoff 晚于 now-115min）场次 < 阈值时，为每个联赛补
    2 场进行中 + 2 场未开始，保证任何时刻都有实时比赛可看。
    返回新建场次。
    """
    now = datetime.now(UTC)
    window_start = now - timedelta(minutes=115)   # 一场球从开球到完赛约 113 分钟
    active = db.query(Match).filter(Match.kickoff_at > window_start).count()
    if active >= 10:
        return 0

    # 已被未完赛比赛占用的球队，避免同一球队同时踢两场
    busy: set[int] = set()
    for tid, in db.query(Match.home_team_id).filter(Match.kickoff_at > window_start):
        busy.add(tid)
    for tid, in db.query(Match.away_team_id).filter(Match.kickoff_at > window_start):
        busy.add(tid)

    rng = random.Random(int(now.timestamp()) ^ 20260927)
    created = 0
    match_no = db.query(Match).count()

    for league in db.query(League).all():
        teams = db.query(Team).filter(Team.league_id == league.id).all()
        rng.shuffle(teams)
        for offset in (-25, -60, +30, +150):
            cands = [t for t in teams if t.id not in busy]
            if len(cands) < 2:
                break
            home, away = cands[0], cands[1]
            busy.update({home.id, away.id})
            match_no += 1
            m = Match(
                league_id=league.id, home_team_id=home.id, away_team_id=away.id,
                kickoff_at=now + timedelta(minutes=offset),
                venue=home.stadium, round=f"Regular Season - {10 + match_no % 4}",
                sim_seed=rng.randint(1, 10**9),
            )
            db.add(m)
            db.flush()

            ratings = {r.team_id: r for r in db.query(TeamRating).filter(
                TeamRating.team_id.in_([home.id, away.id])).all()}
            form = lambda t: (  # noqa: E731
                (ratings[t.id].breakdown or {}).get("season", {}).get("wins", 6) / 20.0
                if t.id in ratings else 0.5
            )
            pred = prematch(home.elo_rating, away.elo_rating,
                            form_home=form(home), form_away=form(away))
            try:
                from app.ml.train import blend, predict_proba

                ml = predict_proba(
                    home.elo_rating - away.elo_rating,
                    form(home), form(away),
                )
                pred = blend(pred, ml)
            except Exception as e:
                pred["model_version"] = "dc-only-v0.1"
                print(f"[topup] ML blend skipped: {e}")
            db.add(MatchPrediction(match_id=m.id, **pred))

            squads = {
                "home": db.query(Player).filter(Player.team_id == home.id).all(),
                "away": db.query(Player).filter(Player.team_id == away.id).all(),
            }
            db.add_all(generate_events(
                random.Random(m.sim_seed), m, squads,
                pred["lambda_home"], pred["lambda_away"],
            ))
            created += 1

    db.commit()
    if created:
        print(f"[topup] 补赛 {created} 场（各联赛 2 进行中 + 2 未开始）")
    return created
