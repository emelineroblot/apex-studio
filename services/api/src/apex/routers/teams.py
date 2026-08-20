"""`GET/POST /teams` (+ `/{id}`) — référentiel, écriture `owner` uniquement (§3-I)."""

from fastapi import APIRouter, Query, Security

from apex.routers._common import bearer_scheme, not_implemented
from apex.schemas.catalog import TeamCreate, TeamOut
from apex.schemas.common import Page

router = APIRouter(prefix="/teams", tags=["teams"], dependencies=[Security(bearer_scheme)])


@router.get("", response_model=Page[TeamOut], summary="Liste des écuries")
def list_teams(cursor: str | None = None, limit: int = Query(default=50, le=100)) -> Page[TeamOut]:
    not_implemented("GET /teams")


@router.post("", response_model=TeamOut, status_code=201, summary="Créer une écurie")
def create_team(payload: TeamCreate) -> TeamOut:
    not_implemented("POST /teams")


@router.get("/{team_id}", response_model=TeamOut, summary="Fiche écurie")
def get_team(team_id: int) -> TeamOut:
    not_implemented("GET /teams/{id}")
