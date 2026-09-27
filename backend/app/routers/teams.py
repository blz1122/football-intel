"""球队 / 球员 Profile 路由（Phase 3）。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import League, Player, Team, TeamRating
from app.schemas import (
    LeagueBrief,
    PlayerBrief,
    PlayerListItem,
    PlayerProfile,
    TeamListItem,
    TeamProfile,
    TeamRadar,
)

router = APIRouter(prefix="/api/v1", tags=["teams"])


def _player_brief(p: Player) -> PlayerBrief:
    return PlayerBrief(
        id=p.id, name=p.name, name_en=p.name_en, position=p.position,
        number=p.number, ai_rating=p.ai_rating, season_stats=p.season_stats or {},
    )


def _real_mode(db: Session) -> set[int]:
    """真实数据源生效时，返回参与真实比赛的球队 id 集合（空集表示模拟模式）。"""
    from app.models import Match

    rows = (
        db.query(Match.home_team_id, Match.away_team_id)
        .filter(Match.provider == "espn")
        .all()
    )
    ids: set[int] = set()
    for h, a in rows:
        ids.add(h)
        ids.add(a)
    return ids


@router.get("/teams", response_model=list[TeamListItem])
def list_teams(league_id: int | None = None, db: Session = Depends(get_db)):
    """球队列表（可按联赛过滤），按 TPI 降序。

    接入真实数据源时只返回真实赛程中出现的球队，避免混入模拟球队。"""
    q = db.query(Team).order_by(Team.id)
    if league_id:
        q = q.filter(Team.league_id == league_id)
    real_ids = _real_mode(db)
    if real_ids:
        q = q.filter(Team.id.in_(real_ids))
    ratings = {r.team_id: r.tpi for r in db.query(TeamRating).all()}
    out = []
    for t in q.all():
        out.append(TeamListItem(
            id=t.id, name=t.name, name_en=t.name_en, short_name=t.short_name,
            color=t.color, elo_rating=t.elo_rating, stadium=t.stadium,
            league=LeagueBrief(id=t.league.id, name=t.league.name,
                               short_name=t.league.short_name),
            tpi=ratings.get(t.id),
        ))
    out.sort(key=lambda x: x.tpi or 0, reverse=True)
    return out


@router.get("/players", response_model=list[PlayerListItem])
def list_players(
    league_id: int | None = None,
    team_id: int | None = None,
    position: str | None = None,
    db: Session = Depends(get_db),
):
    """球员列表（可按联赛/球队/位置过滤），按 AI 评分降序。"""
    q = db.query(Player).join(Team, Player.team_id == Team.id)
    if team_id:
        q = q.filter(Player.team_id == team_id)
    if league_id:
        q = q.filter(Team.league_id == league_id)
    if position:
        q = q.filter(Player.position == position)
    real_ids = _real_mode(db)
    if real_ids:
        q = q.filter(Player.team_id.in_(real_ids), Player.provider == "espn")
    players = q.all()
    players.sort(key=lambda p: p.ai_rating or 0, reverse=True)
    return [
        PlayerListItem(
            id=p.id, name=p.name, name_en=p.name_en, position=p.position,
            number=p.number, age=p.age, ai_rating=p.ai_rating,
            season_stats=p.season_stats or {},
            team_id=p.team.id, team_name=p.team.name,
            team_short=p.team.short_name, team_color=p.team.color,
            league_short=p.team.league.short_name,
        )
        for p in players
    ]


@router.get("/teams/{team_id}", response_model=TeamProfile)
def team_profile(team_id: int, db: Session = Depends(get_db)):
    t = db.get(Team, team_id)
    if not t:
        raise HTTPException(404, "TEAM_NOT_FOUND")
    rating = db.query(TeamRating).filter(TeamRating.team_id == team_id).first()
    if not rating:
        raise HTTPException(404, "RATING_NOT_READY")
    squad = (
        db.query(Player)
        .filter(Player.team_id == team_id)
        .order_by(Player.position, Player.number)
        .all()
    )
    # 真实数据源模式下只展示真实阵容，避免混入模拟球员
    if _real_mode(db):
        real_squad = [p for p in squad if p.provider == "espn"]
        if real_squad:
            squad = real_squad
    # 前锋->中场->后卫->门将 展示顺序
    order = {"FW": 0, "MF": 1, "DF": 2, "GK": 3}
    squad.sort(key=lambda p: (order.get(p.position, 9), p.number))
    return TeamProfile(
        id=t.id, name=t.name, name_en=t.name_en, short_name=t.short_name,
        color=t.color,
        league=LeagueBrief(id=t.league.id, name=t.league.name,
                           short_name=t.league.short_name),
        elo_rating=t.elo_rating, stadium=t.stadium,
        tpi=rating.tpi,
        radar=TeamRadar(
            attack=rating.attack, defense=rating.defense,
            possession=rating.possession, pressing=rating.pressing,
            efficiency=rating.efficiency, form=rating.form,
        ),
        breakdown=rating.breakdown or {},
        squad=[_player_brief(p) for p in squad],
    )


@router.get("/players/{player_id}", response_model=PlayerProfile)
def player_profile(player_id: int, db: Session = Depends(get_db)):
    p = db.get(Player, player_id)
    if not p:
        raise HTTPException(404, "PLAYER_NOT_FOUND")
    t = p.team
    rating = db.query(TeamRating).filter(TeamRating.team_id == t.id).first() if t else None
    radar = None
    tpi = None
    if rating:
        tpi = rating.tpi
        radar = TeamRadar(
            attack=rating.attack, defense=rating.defense,
            possession=rating.possession, pressing=rating.pressing,
            efficiency=rating.efficiency, form=rating.form,
        )
    return PlayerProfile(
        id=p.id, name=p.name, name_en=p.name_en, position=p.position,
        number=p.number, age=p.age,
        team={
            "id": t.id, "name": t.name, "name_en": t.name_en,
            "short_name": t.short_name, "color": t.color,
            "elo_rating": t.elo_rating, "tpi": tpi, "radar": radar,
        } if t else None,
        ai_rating=p.ai_rating, season_stats=p.season_stats or {},
    )


@router.get("/leaderboard/tpi")
def tpi_leaderboard(league_id: int | None = None, db: Session = Depends(get_db)):
    """TPI 排行榜（可按联赛过滤）。"""
    q = db.query(TeamRating, Team).join(Team, TeamRating.team_id == Team.id)
    if league_id:
        q = q.filter(Team.league_id == league_id)
    rows = q.order_by(TeamRating.tpi.desc()).limit(20).all()
    return [
        {
            "team_id": r.Team.id, "name": r.Team.name, "short_name": r.Team.short_name,
            "color": r.Team.color, "league": r.Team.league.short_name,
            "tpi": r.TeamRating.tpi, "attack": r.TeamRating.attack,
            "defense": r.TeamRating.defense, "form": r.TeamRating.form,
        }
        for r in rows
    ]
