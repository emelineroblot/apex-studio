"""`shooting` — CRUD, équipe affectée, engagements (clé métier du projet, §3-I, §3-F.3).

Cloisonnement photographe : `owner` voit tout, `photographer` uniquement ses shootings
affectés (`shooting_staff`) — appliqué au Lot 1 via `services/access.py`.
"""

from fastapi import APIRouter, File, Query, Security, UploadFile

from apex.routers._common import bearer_scheme, not_implemented
from apex.schemas.common import Page
from apex.schemas.shooting import (
    EngagementCreate,
    EngagementImportResult,
    EngagementOut,
    ShootingCreate,
    ShootingOut,
    ShootingPatch,
    ShootingSummary,
    StaffUpdateRequest,
    StaffUpdateResponse,
)

router = APIRouter(prefix="/shootings", tags=["shootings"], dependencies=[Security(bearer_scheme)])


@router.get("", response_model=Page[ShootingSummary], summary="Liste des shootings")
def list_shootings(
    client_id: int | None = None,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    status: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, le=100),
) -> Page[ShootingSummary]:
    not_implemented("GET /shootings")


@router.post("", response_model=ShootingOut, status_code=201, summary="Créer un shooting")
def create_shooting(payload: ShootingCreate) -> ShootingOut:
    not_implemented("POST /shootings")


@router.get("/{shooting_id}", response_model=ShootingOut, summary="Fiche shooting")
def get_shooting(shooting_id: int) -> ShootingOut:
    not_implemented("GET /shootings/{id}")


@router.patch("/{shooting_id}", response_model=ShootingOut, summary="Modifier un shooting")
def patch_shooting(shooting_id: int, payload: ShootingPatch) -> ShootingOut:
    not_implemented("PATCH /shootings/{id}")


@router.put(
    "/{shooting_id}/staff",
    response_model=StaffUpdateResponse,
    summary="Affecter l'équipe au shooting",
)
def put_shooting_staff(shooting_id: int, payload: StaffUpdateRequest) -> StaffUpdateResponse:
    not_implemented("PUT /shootings/{id}/staff")


@router.get(
    "/{shooting_id}/engagements",
    response_model=list[EngagementOut],
    summary="Engagements du shooting",
)
def list_engagements(shooting_id: int) -> list[EngagementOut]:
    not_implemented("GET /shootings/{id}/engagements")


@router.post(
    "/{shooting_id}/engagements",
    response_model=EngagementOut,
    status_code=201,
    summary="Créer un engagement",
)
def create_engagement(shooting_id: int, payload: EngagementCreate) -> EngagementOut:
    not_implemented("POST /shootings/{id}/engagements")


@router.post(
    "/{shooting_id}/engagements:import",
    response_model=EngagementImportResult,
    summary="Import CSV des engagements (`car_number,driver,team,client,car_model`)",
)
def import_engagements(shooting_id: int, file: UploadFile = File(...)) -> EngagementImportResult:
    not_implemented("POST /shootings/{id}/engagements:import")
