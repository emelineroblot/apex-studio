"""`PATCH/DELETE /engagements/{id}` — la création vit sous `/shootings/{id}/engagements`."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apex.db import get_db
from apex.models.shooting import Engagement
from apex.schemas.shooting import EngagementOut, EngagementPatch
from apex.security import CurrentUser
from apex.services import access

router = APIRouter(prefix="/engagements", tags=["engagements"])


def _get_or_404(db: Session, engagement_id: int) -> Engagement:
    engagement = db.execute(
        select(Engagement).where(Engagement.id == engagement_id)
    ).scalar_one_or_none()
    if engagement is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "Engagement introuvable.", "detail": None},
        )
    return engagement


@router.patch("/{engagement_id}", response_model=EngagementOut, summary="Modifier un engagement")
def patch_engagement(
    engagement_id: int, payload: EngagementPatch, user: CurrentUser, db: Session = Depends(get_db)
) -> EngagementOut:
    engagement = _get_or_404(db, engagement_id)
    access.assert_can_write_engagements(db, user, engagement.shooting_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(engagement, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "duplicate_car_number",
                "message": "Ce numéro existe déjà sur ce shooting.",
                "detail": None,
            },
        ) from exc
    db.refresh(engagement)
    return EngagementOut.model_validate(engagement)


@router.delete("/{engagement_id}", status_code=204, summary="Supprimer un engagement")
def delete_engagement(engagement_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> None:
    engagement = _get_or_404(db, engagement_id)
    access.assert_can_write_engagements(db, user, engagement.shooting_id)
    db.delete(engagement)
    db.commit()
