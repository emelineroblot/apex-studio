"""`GET/POST /drivers` (+ `/{id}`) — référentiel, écriture `owner` uniquement (§3-I)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from apex.db import get_db
from apex.models.catalog import Driver
from apex.schemas.catalog import DriverCreate, DriverOut
from apex.schemas.common import Page
from apex.security import CurrentUser, require_role
from apex.services.pagination import paginate_by_id

router = APIRouter(prefix="/drivers", tags=["drivers"])


@router.get("", response_model=Page[DriverOut], summary="Liste des pilotes")
def list_drivers(
    user: CurrentUser,
    db: Session = Depends(get_db),
    cursor: str | None = None,
    limit: int = Query(default=50, le=100),
) -> Page[DriverOut]:
    items, next_cursor = paginate_by_id(db, select(Driver), Driver.id, cursor=cursor, limit=limit)
    return Page(items=[DriverOut.model_validate(d) for d in items], next_cursor=next_cursor)


@router.post(
    "",
    response_model=DriverOut,
    status_code=201,
    summary="Créer un pilote",
    dependencies=[require_role("owner")],
)
def create_driver(payload: DriverCreate, db: Session = Depends(get_db)) -> DriverOut:
    driver = Driver(**payload.model_dump())
    db.add(driver)
    db.commit()
    db.refresh(driver)
    return DriverOut.model_validate(driver)


@router.get("/{driver_id}", response_model=DriverOut, summary="Fiche pilote")
def get_driver(driver_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> DriverOut:
    driver = db.execute(select(Driver).where(Driver.id == driver_id)).scalar_one_or_none()
    if driver is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "Pilote introuvable.", "detail": None},
        )
    return DriverOut.model_validate(driver)
