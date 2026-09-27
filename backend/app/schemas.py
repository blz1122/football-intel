"""Pydantic 响应模型（API 契约，前端 lib/types.ts 与之对齐）。"""
from datetime import datetime

from pydantic import BaseModel


class TeamBrief(BaseModel):
    id: int
    name: str
    short_name: str
    color: str
    elo_rating: float


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
    player: str | None
    related_player: str | None
    detail: str | None


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
