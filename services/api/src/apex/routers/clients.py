"""CRUD `client` — lecture/écriture `owner`, lecture seule `photographer` (§3-I)."""

from fastapi import APIRouter, Query, Security

from apex.routers._common import bearer_scheme, not_implemented
from apex.schemas.catalog import ClientCreate, ClientOut, ClientUpdate
from apex.schemas.common import Page

router = APIRouter(prefix="/clients", tags=["clients"], dependencies=[Security(bearer_scheme)])


@router.get("", response_model=Page[ClientOut], summary="Liste des clients")
def list_clients(
    cursor: str | None = None, limit: int = Query(default=50, le=100)
) -> Page[ClientOut]:
    not_implemented("GET /clients")


@router.post("", response_model=ClientOut, status_code=201, summary="Créer un client")
def create_client(payload: ClientCreate) -> ClientOut:
    not_implemented("POST /clients")


@router.get("/{client_id}", response_model=ClientOut, summary="Fiche client")
def get_client(client_id: int) -> ClientOut:
    not_implemented("GET /clients/{id}")


@router.patch("/{client_id}", response_model=ClientOut, summary="Modifier un client")
def patch_client(client_id: int, payload: ClientUpdate) -> ClientOut:
    not_implemented("PATCH /clients/{id}")


@router.delete("/{client_id}", status_code=204, summary="Supprimer un client")
def delete_client(client_id: int) -> None:
    not_implemented("DELETE /clients/{id}")
