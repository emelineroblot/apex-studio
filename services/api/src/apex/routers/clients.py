"""CRUD `client` — lecture/écriture `owner`, lecture seule `photographer` (§3-I)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from apex.db import get_db
from apex.models.catalog import Client
from apex.schemas.catalog import ClientCreate, ClientOut, ClientUpdate
from apex.schemas.common import Page
from apex.security import CurrentUser, require_role
from apex.services.pagination import paginate_by_id

router = APIRouter(prefix="/clients", tags=["clients"])


def _get_or_404(db: Session, client_id: int) -> Client:
    client = db.execute(select(Client).where(Client.id == client_id)).scalar_one_or_none()
    if client is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "Client introuvable.", "detail": None},
        )
    return client


@router.get("", response_model=Page[ClientOut], summary="Liste des clients")
def list_clients(
    user: CurrentUser,
    db: Session = Depends(get_db),
    cursor: str | None = None,
    limit: int = Query(default=50, le=100),
) -> Page[ClientOut]:
    items, next_cursor = paginate_by_id(db, select(Client), Client.id, cursor=cursor, limit=limit)
    return Page(items=[ClientOut.model_validate(c) for c in items], next_cursor=next_cursor)


@router.post(
    "",
    response_model=ClientOut,
    status_code=201,
    summary="Créer un client",
    dependencies=[require_role("owner")],
)
def create_client(payload: ClientCreate, db: Session = Depends(get_db)) -> ClientOut:
    client = Client(**payload.model_dump())
    db.add(client)
    db.commit()
    db.refresh(client)
    return ClientOut.model_validate(client)


@router.get("/{client_id}", response_model=ClientOut, summary="Fiche client")
def get_client(client_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> ClientOut:
    return ClientOut.model_validate(_get_or_404(db, client_id))


@router.patch(
    "/{client_id}",
    response_model=ClientOut,
    summary="Modifier un client",
    dependencies=[require_role("owner")],
)
def patch_client(client_id: int, payload: ClientUpdate, db: Session = Depends(get_db)) -> ClientOut:
    client = _get_or_404(db, client_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, field, value)
    db.commit()
    db.refresh(client)
    return ClientOut.model_validate(client)


@router.delete(
    "/{client_id}",
    status_code=204,
    summary="Supprimer un client",
    dependencies=[require_role("owner")],
)
def delete_client(client_id: int, db: Session = Depends(get_db)) -> None:
    client = _get_or_404(db, client_id)
    db.delete(client)
    db.commit()
