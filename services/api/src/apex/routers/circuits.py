"""`GET/POST /circuits` (+ `/{id}`) — référentiel, écriture `owner` uniquement (§3-I)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from apex.db import get_db
from apex.models.catalog import Circuit
from apex.schemas.catalog import CircuitCreate, CircuitOut
from apex.schemas.common import Page
from apex.security import CurrentUser, require_role
from apex.services.pagination import paginate_by_id

router = APIRouter(prefix="/circuits", tags=["circuits"])


@router.get("", response_model=Page[CircuitOut], summary="Liste des circuits")
def list_circuits(
    user: CurrentUser,
    db: Session = Depends(get_db),
    cursor: str | None = None,
    limit: int = Query(default=50, le=100),
) -> Page[CircuitOut]:
    items, next_cursor = paginate_by_id(db, select(Circuit), Circuit.id, cursor=cursor, limit=limit)
    return Page(items=[CircuitOut.model_validate(c) for c in items], next_cursor=next_cursor)


@router.post(
    "",
    response_model=CircuitOut,
    status_code=201,
    summary="Créer un circuit",
    dependencies=[require_role("owner")],
)
def create_circuit(payload: CircuitCreate, db: Session = Depends(get_db)) -> CircuitOut:
    circuit = Circuit(**payload.model_dump())
    db.add(circuit)
    db.commit()
    db.refresh(circuit)
    return CircuitOut.model_validate(circuit)


@router.get("/{circuit_id}", response_model=CircuitOut, summary="Fiche circuit")
def get_circuit(circuit_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> CircuitOut:
    circuit = db.execute(select(Circuit).where(Circuit.id == circuit_id)).scalar_one_or_none()
    if circuit is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "Circuit introuvable.", "detail": None},
        )
    return CircuitOut.model_validate(circuit)
