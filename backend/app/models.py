"""SQLAlchemy ORM 模型 —— 与 db/schema.sql 对齐（SQLite 兼容：JSONB→JSON, NUMERIC→Float）。"""
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class League(Base):
    __tablename__ = "leagues"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))        # 中文名（展示）
    name_en: Mapped[str] = mapped_column(String(80), default="")
    short_name: Mapped[str] = mapped_column(String(16))
    country: Mapped[str] = mapped_column(String(60))
    logo_url: Mapped[str | None] = mapped_column(String(255), nullable=True)

    teams: Mapped[list["Team"]] = relationship(back_populates="league")


class Season(Base):
    __tablename__ = "seasons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    name: Mapped[str] = mapped_column(String(20))
    start_date: Mapped[Date] = mapped_column(Date)
    end_date: Mapped[Date] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    name: Mapped[str] = mapped_column(String(80))        # 中文名（展示）
    name_en: Mapped[str] = mapped_column(String(80), default="")
    short_name: Mapped[str] = mapped_column(String(8))
    country: Mapped[str] = mapped_column(String(60))
    color: Mapped[str] = mapped_column(String(9), default="#3b4b70")  # 主题色
    stadium: Mapped[str | None] = mapped_column(String(80), nullable=True)
    fifa_ranking: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    elo_rating: Mapped[float] = mapped_column(Float, default=1700.0)

    league: Mapped[League] = relationship(back_populates="teams")
    players: Mapped[list["Player"]] = relationship(back_populates="team")


class Player(Base):
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    name: Mapped[str] = mapped_column(String(80))        # 中文名（展示）
    name_en: Mapped[str] = mapped_column(String(80), default="")
    position: Mapped[str] = mapped_column(String(2))  # GK/DF/MF/FW
    number: Mapped[int] = mapped_column(SmallInteger)
    age: Mapped[int] = mapped_column(SmallInteger, default=25)
    rating: Mapped[float] = mapped_column(Float, default=7.0)  # 基础能力 6-8.5
    ai_rating: Mapped[float] = mapped_column(Float, default=6.5)  # AI Player Rating 0-10
    season_stats: Mapped[dict] = mapped_column(JSON, default=dict)  # 赛季汇总
    status: Mapped[str] = mapped_column(String(12), default="normal")  # normal/injured/suspended
    injury_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    team: Mapped[Team] = relationship(back_populates="players")


class Match(Base):
    __tablename__ = "matches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    venue: Mapped[str | None] = mapped_column(String(80), nullable=True)
    round: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sim_seed: Mapped[int] = mapped_column(Integer)  # 模拟器确定性种子

    league: Mapped[League] = relationship()
    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id])
    events: Mapped[list["MatchEvent"]] = relationship(
        back_populates="match", order_by="MatchEvent.minute"
    )
    prediction: Mapped["MatchPrediction | None"] = relationship(back_populates="match")


class MatchEvent(Base):
    __tablename__ = "match_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    minute: Mapped[int] = mapped_column(SmallInteger)
    side: Mapped[str] = mapped_column(String(4))  # home/away
    type: Mapped[str] = mapped_column(String(16))  # goal/yellow_card/red_card/substitution
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    related_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id"), nullable=True
    )
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    x: Mapped[float | None] = mapped_column(Float, nullable=True)  # 射门/进球坐标(进攻方向归一)
    y: Mapped[float | None] = mapped_column(Float, nullable=True)

    match: Mapped[Match] = relationship(back_populates="events")
    player: Mapped[Player | None] = relationship(foreign_keys=[player_id])


class MatchPrediction(Base):
    __tablename__ = "match_predictions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id"), unique=True, index=True
    )
    model_version: Mapped[str] = mapped_column(String(32), default="elo-poisson-v0.1")
    p_home: Mapped[float] = mapped_column(Float)
    p_draw: Mapped[float] = mapped_column(Float)
    p_away: Mapped[float] = mapped_column(Float)
    lambda_home: Mapped[float] = mapped_column(Float)
    lambda_away: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    expected_score: Mapped[str] = mapped_column(String(8))
    score_matrix: Mapped[dict] = mapped_column(JSON)  # {"1-0": 0.11, ...} 前6x6

    match: Mapped[Match] = relationship(back_populates="prediction")


class WinProbSnapshot(Base):
    __tablename__ = "win_probability_snapshots"
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id"), primary_key=True
    )
    minute: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    p_home: Mapped[float] = mapped_column(Float)
    p_draw: Mapped[float] = mapped_column(Float)
    p_away: Mapped[float] = mapped_column(Float)
    trigger: Mapped[str] = mapped_column(String(12), default="minute")


class TeamRating(Base):
    """Team Power Index 及分项（Phase 3）。"""
    __tablename__ = "team_ratings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    tpi: Mapped[float] = mapped_column(Float)          # 综合 0-100
    attack: Mapped[float] = mapped_column(Float)
    defense: Mapped[float] = mapped_column(Float)
    form: Mapped[float] = mapped_column(Float)
    possession: Mapped[float] = mapped_column(Float, default=50)
    pressing: Mapped[float] = mapped_column(Float, default=50)
    efficiency: Mapped[float] = mapped_column(Float, default=50)
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict)  # 赛季明细 + 近10场


class MonteCarloResult(Base):
    """Monte Carlo 模拟结果缓存（Phase 3）。"""
    __tablename__ = "monte_carlo_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id"), unique=True, index=True
    )
    simulations: Mapped[int] = mapped_column(Integer, default=10000)
    p_home: Mapped[float] = mapped_column(Float)
    p_draw: Mapped[float] = mapped_column(Float)
    p_away: Mapped[float] = mapped_column(Float)
    score_matrix: Mapped[dict] = mapped_column(JSON)   # {"1-0": 0.23, ...}
    over_under: Mapped[dict] = mapped_column(JSON)     # {"0.5": ..., "2.5": ...}
    btts: Mapped[float] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String(32), default="dc-mc-v0.2")
