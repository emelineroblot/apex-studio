"""`GET/POST /teams` (+ `/{id}`) — référentiel, écriture `owner` uniquement (§3-I)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from apex.db import get_db
from apex.models.catalog import Team
from apex.schemas.catalog import TeamCreate, TeamOut
from apex.schemas.common import Page
from apex.security import CurrentUser, require_role
from apex.services.pagination import paginate_by_id

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("", response_model=Page[TeamOut], summary="Liste des écuries")
def list_teams(
    user: CurrentUser,
    db: Session = Depends(get_db),
    cursor: str | None = None,
    limit: int = Query(default=50, le=100),
) -> Page[TeamOut]:
    items, next_cursor, total = paginate_by_id(
        db, select(Team), Team.id, cursor=cursor, limit=limit, with_total=True
    )
    return Page(
        items=[TeamOut.model_validate(t) for t in items], next_cursor=next_cursor, total=total
    )


@router.post(
    "",
    response_model=TeamOut,
    status_code=201,
    summary="Créer une écurie",
    dependencies=[require_role("owner")],
)
def create_team(payload: TeamCreate, db: Session = Depends(get_db)) -> TeamOut:
    team = Team(**payload.model_dump())
    db.add(team)
    db.commit()
    db.refresh(team)
    return TeamOut.model_validate(team)


@router.get("/{team_id}", response_model=TeamOut, summary="Fiche écurie")
def get_team(team_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> TeamOut:
    team = db.execute(select(Team).where(Team.id == team_id)).scalar_one_or_none()
    if team is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "Écurie introuvable.", "detail": None},
        )
    return TeamOut.model_validate(team)
