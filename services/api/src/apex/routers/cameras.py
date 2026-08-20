"""`GET /cameras`, `PATCH /cameras/{id}` — décalage d'horloge, corrige rétroactivement le
rattachement (§3-F.3) via l'enqueue de `reattach_camera`.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from apex.db import get_db
from apex.models.catalog import Camera
from apex.queue.enqueue import enqueue, enqueue_unique_pending
from apex.schemas.catalog import CameraOut, CameraPatch, CameraPatchResponse
from apex.security import CurrentUser
from apex.services import access

router = APIRouter(prefix="/cameras", tags=["cameras"])


@router.get("", response_model=list[CameraOut], summary="Liste des boîtiers")
def list_cameras(user: CurrentUser, db: Session = Depends(get_db)) -> list[CameraOut]:
    cameras = db.execute(select(Camera).order_by(Camera.id)).scalars().all()
    return [CameraOut.model_validate(c) for c in cameras]


@router.patch(
    "/{camera_id}",
    response_model=CameraPatchResponse,
    summary="Régler le décalage d'horloge / la propriété d'un boîtier",
)
def patch_camera(
    camera_id: int, payload: CameraPatch, user: CurrentUser, db: Session = Depends(get_db)
) -> CameraPatchResponse:
    camera = db.execute(select(Camera).where(Camera.id == camera_id)).scalar_one_or_none()
    if camera is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "Boîtier introuvable.", "detail": None},
        )
    if payload.owner_user_id is not None:
        access.require_owner(user, message="Seul le dirigeant peut réaffecter un boîtier.")

    offset_changed = (
        payload.clock_offset_seconds is not None
        and payload.clock_offset_seconds != camera.clock_offset_seconds
    )

    if payload.clock_offset_seconds is not None:
        camera.clock_offset_seconds = payload.clock_offset_seconds
    if payload.timezone is not None:
        camera.timezone = payload.timezone
    if payload.owner_user_id is not None:
        camera.owner_user_id = payload.owner_user_id

    reattach_job_id: int | None = None
    if offset_changed:
        # Enqueue transactionnel avec l'écriture métier qui le justifie (§3-F.3, §3-E.4.2).
        dedupe_key = f"camera:{camera.id}"
        reattach_job_id = enqueue(
            db,
            "reattach_camera",
            {"camera_id": camera.id},
            dedupe_key=dedupe_key,
            priority=90,
        )
        if reattach_job_id is None:
            # Un job de recalcul est déjà en file pour ce boîtier — pas un doublon d'effort,
            # l'UI peut suivre le job existant.
            reattach_job_id = enqueue_unique_pending(db, "reattach_camera", dedupe_key)

    db.commit()
    db.refresh(camera)
    return CameraPatchResponse(
        camera=CameraOut.model_validate(camera), reattach_job_id=reattach_job_id
    )
