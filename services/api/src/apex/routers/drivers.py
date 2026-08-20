"""`GET/POST /drivers` (+ `/{id}`) — référentiel, écriture `owner` uniquement (§3-I)."""

from fastapi import APIRouter, Query, Security

from apex.routers._common import bearer_scheme, not_implemented
from apex.schemas.catalog import DriverCreate, DriverOut
from apex.schemas.common import Page

router = APIRouter(prefix="/drivers", tags=["drivers"], dependencies=[Security(bearer_scheme)])


@router.get("", response_model=Page[DriverOut], summary="Liste des pilotes")
def list_drivers(
    cursor: str | None = None, limit: int = Query(default=50, le=100)
) -> Page[DriverOut]:
    not_implemented("GET /drivers")


@router.post("", response_model=DriverOut, status_code=201, summary="Créer un pilote")
def create_driver(payload: DriverCreate) -> DriverOut:
    not_implemented("POST /drivers")


@router.get("/{driver_id}", response_model=DriverOut, summary="Fiche pilote")
def get_driver(driver_id: int) -> DriverOut:
    not_implemented("GET /drivers/{id}")
