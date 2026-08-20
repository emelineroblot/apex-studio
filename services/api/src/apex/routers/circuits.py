"""`GET/POST /circuits` (+ `/{id}`) — référentiel, écriture `owner` uniquement (§3-I)."""

from fastapi import APIRouter, Query, Security

from apex.routers._common import bearer_scheme, not_implemented
from apex.schemas.catalog import CircuitCreate, CircuitOut
from apex.schemas.common import Page

router = APIRouter(prefix="/circuits", tags=["circuits"], dependencies=[Security(bearer_scheme)])


@router.get("", response_model=Page[CircuitOut], summary="Liste des circuits")
def list_circuits(
    cursor: str | None = None, limit: int = Query(default=50, le=100)
) -> Page[CircuitOut]:
    not_implemented("GET /circuits")


@router.post("", response_model=CircuitOut, status_code=201, summary="Créer un circuit")
def create_circuit(payload: CircuitCreate) -> CircuitOut:
    not_implemented("POST /circuits")


@router.get("/{circuit_id}", response_model=CircuitOut, summary="Fiche circuit")
def get_circuit(circuit_id: int) -> CircuitOut:
    not_implemented("GET /circuits/{id}")
