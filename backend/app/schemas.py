"""Pydantic 响应模型（API 契约，前端 lib/types.ts 与之对齐）。"""
from datetime import datetime

from pydantic import BaseModel


class TeamRadar(BaseModel):
    attack: float
    defense: float
    possession: float
    pressing: float
    efficiency: float
    form: float


class TeamBrief(BaseModel):
    id: int
    name: str
    name_en: str
    short_name: str
    color: str
    elo_rating: float
    tpi: float | None = None
    radar: TeamRadar | None = None


class LeagueBrief(BaseModel):
    id: int
    name: str
    short_name: str


class WinProb(BaseModel):
    home: float
    draw: float
    away: float


class LiveStats(BaseModel):
    minute: int
    possession_home: int
    shots_home: int
    shots_away: int
    shots_on_target_home: int
    shots_on_target_away: int
    corners_home: int
    corners_away: int
    fouls_home: int
    fouls_away: int
    yellow_home: int
    yellow_away: int
    red_home: int
    red_away: int
    dangerous_home: int
    dangerous_away: int
    xg_home: float
    xg_away: float


class MatchListItem(BaseModel):
    id: int
    league: LeagueBrief
    round: str | None
    kickoff_at: datetime
    status: str  # scheduled/live/halftime/finished
    period: str | None  # 1H/HT/2H/FT
    minute: int | None
    home_score: int
    away_score: int
    home_team: TeamBrief
    away_team: TeamBrief
    win_prob: WinProb
    live_stats: LiveStats | None = None
    is_hot: bool = False


class EventOut(BaseModel):
    minute: int
    side: str
    type: str
    player_id: int | None = None
    player: str | None
    related_player_id: int | None = None
    related_player: str | None
    detail: str | None
    # ESPN 原始文本是英文，这里给出中文译文（前端优先展示）
    detail_cn: str | None = None


class StatsPoint(LiveStats):
    pass


class PredictionOut(BaseModel):
    model_version: str
    p_home: float
    p_draw: float
    p_away: float
    lambda_home: float
    lambda_away: float
    confidence: float
    expected_score: str
    score_matrix: dict


class MatchDetail(BaseModel):
    match: MatchListItem
    events: list[EventOut]
    prediction: PredictionOut | None


class CurvePoint(BaseModel):
    minute: int
    p_home: float
    p_draw: float
    p_away: float
    trigger: str


class ShotOut(BaseModel):
    x: float
    y: float
    xg: float
    goal: bool


class ShotMap(BaseModel):
    home: list[ShotOut]
    away: list[ShotOut]


class Kpis(BaseModel):
    total_today: int
    live_now: int
    finished_today: int
    accuracy_7d: float
    brier_score: float


class PredictionRankItem(BaseModel):
    match_id: int
    title: str
    pick: str
    probability: float
    kickoff_at: datetime


# ---------------- Phase 3：模拟 / 球队 / 球员 ----------------

class MonteCarloOut(BaseModel):
    match_id: int
    simulations: int
    p_home: float
    p_draw: float
    p_away: float
    score_matrix: dict          # {"2-1": 0.12, ...} 按概率降序
    over_under: dict            # {"0.5": .., "2.5": ..}
    btts: float
    model_version: str


class PlayerBrief(BaseModel):
    id: int
    name: str
    name_en: str
    position: str
    number: int
    ai_rating: float
    season_stats: dict


class TeamProfile(BaseModel):
    id: int
    name: str
    name_en: str
    short_name: str
    color: str
    league: LeagueBrief
    elo_rating: float
    stadium: str | None
    tpi: float
    radar: TeamRadar
    breakdown: dict             # season 明细 + form_last10
    squad: list[PlayerBrief]


class PlayerProfile(BaseModel):
    id: int
    name: str
    name_en: str
    position: str
    number: int
    age: int
    team: TeamBrief
    ai_rating: float
    season_stats: dict


# ---------------- 列表页（球队/球员浏览） ----------------

class TeamListItem(BaseModel):
    id: int
    name: str
    name_en: str
    short_name: str
    color: str
    elo_rating: float
    stadium: str | None
    league: LeagueBrief
    tpi: float | None = None


class PlayerListItem(BaseModel):
    id: int
    name: str
    name_en: str
    position: str
    number: int
    age: int
    ai_rating: float
    season_stats: dict
    team_id: int
    team_name: str
    team_short: str
    team_color: str
    league_short: str
