"""`PATCH/DELETE /engagements/{id}` — la création vit sous `/shootings/{id}/engagements`."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apex.db import get_db
from apex.models.media import MediaEngagement
from apex.models.shooting import Engagement
from apex.pipeline.ocr import classify
from apex.schemas.shooting import EngagementOut, EngagementPatch
from apex.security import CurrentUser
from apex.services import access
from apex.services.ocr_settings import load_ocr_settings
from apex.services.search_projection import project_media_search

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


def _media_ids_for_engagement(db: Session, engagement_id: int) -> list[int]:
    rows = db.execute(
        select(MediaEngagement.media_id)
        .where(MediaEngagement.engagement_id == engagement_id)
        .distinct()
    ).scalars()
    return [int(r) for r in rows]


@router.patch("/{engagement_id}", response_model=EngagementOut, summary="Modifier un engagement")
def patch_engagement(
    engagement_id: int, payload: EngagementPatch, user: CurrentUser, db: Session = Depends(get_db)
) -> EngagementOut:
    engagement = _get_or_404(db, engagement_id)
    access.assert_can_write_engagements(db, user, engagement.shooting_id)
    # Revue J2 (🟠 n°2) : `media_search` dénormalise `car_numbers`/`team_ids`/`driver_ids`
    # depuis cette table (§ `search_projection.py`) — capturé **avant** la mutation, le
    # nouvel état est déjà rechargé par la requête de reprojection ci-dessous.
    media_ids = _media_ids_for_engagement(db, engagement_id)
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

    # Corriger un numéro (ou le pilote/l'écurie/le client) laisse les médias déjà rattachés
    # introuvables par la nouvelle valeur tant que `media_search` n'est pas reprojetée —
    # reproduit en revue : « corriger l2 en 12 » laisse les photos introuvables par le n°12.
    if media_ids:
        project_media_search(db, media_ids)
        db.commit()
    return EngagementOut.model_validate(engagement)


@router.delete("/{engagement_id}", status_code=204, summary="Supprimer un engagement")
def delete_engagement(engagement_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> None:
    engagement = _get_or_404(db, engagement_id)
    access.assert_can_write_engagements(db, user, engagement.shooting_id)
    media_ids = _media_ids_for_engagement(db, engagement_id)
    db.delete(engagement)
    db.flush()

    # Revue J2 (🟠 n°2) : `DELETE` cascade sur `media_engagement` (FK `ondelete="CASCADE"`)
    # sans qu'aucun code applicatif ne recalcule quoi que ce soit — un média restait
    # `engagement_attached` avec zéro rattachement, et les candidats OCR encore « machine »
    # qui visaient cet engagement restaient étiquetés `auto`/`review` sans cible (leur
    # `engagement_id` est mis à `NULL` par la cascade `ondelete="SET NULL"`, jamais leur
    # `resolution`). Trois étapes : reprojeter ces candidats (`project_media_batch` relit
    # l'engagement depuis la base, absent, donc les redécide en `not_engaged`), réconcilier
    # `attachment_status` pour les médias qui n'ont plus aucun lien, puis reprojeter la
    # recherche.
    if media_ids:
        classify.project_media_batch(db, media_ids, load_ocr_settings(db))
        classify.reconcile_unlinked_attachment_status(db, media_ids)
        db.flush()
        project_media_search(db, media_ids)
    db.commit()
