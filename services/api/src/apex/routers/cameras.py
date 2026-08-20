"""`GET /cameras`, `PATCH /cameras/{id}` — décalage d'horloge, corrige rétroactivement le
rattachement (§3-F.3) via l'enqueue de `reattach_camera`.

**Corrections revue J1** :
- 🔴 n°6 : mutation et liste étaient accessibles à tout utilisateur authentifié quel que
  soit le boîtier — cloisonnées via `services.access.camera_visibility_clause` /
  `assert_can_mutate_camera`.
- 🟠 : modifier `timezone` seul ne déclenchait pas le recalcul (`clock_offset_seconds`
  était seul testé) ; aucun tick n'était déclenché après l'enqueue (§3-E.7 (a)) ; le
  décompte `reattached` calculé par le handler n'était jamais exposé.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from apex.db import SessionLocal, get_db
from apex.models.catalog import Camera
from apex.models.job import Job
from apex.queue.enqueue import enqueue, enqueue_unique_pending
from apex.queue.runner import drain
from apex.schemas.catalog import CameraOut, CameraPatch, CameraPatchResponse
from apex.security import CurrentUser
from apex.services import access

router = APIRouter(prefix="/cameras", tags=["cameras"])

# Budget court : le tick est déclenché synchronement dans la requête PATCH (§3-E.7 (a))
# pour que « N photos re-rattachées » soit démontrable sans attendre le prochain polling —
# ne doit pas pour autant transformer la mutation en requête longue si la file est chargée.
PATCH_DRAIN_BUDGET = timedelta(seconds=3.0)


@router.get("", response_model=list[CameraOut], summary="Liste des boîtiers")
def list_cameras(user: CurrentUser, db: Session = Depends(get_db)) -> list[CameraOut]:
    stmt = select(Camera).order_by(Camera.id)
    visibility = access.camera_visibility_clause(user)
    if visibility is not None:
        stmt = stmt.where(visibility)
    cameras = db.execute(stmt).scalars().all()
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
    # 🔴 n°6 : cloisonnement — un photographe ne peut muter que les boîtiers qui lui sont
    # affectés ou apparaissent dans ses propres médias visibles ; `404`, jamais `403`
    # (§3-I : ne pas révéler l'existence de la ressource hors périmètre).
    access.assert_can_mutate_camera(db, user, camera)
    if payload.owner_user_id is not None:
        access.require_owner(user, message="Seul le dirigeant peut réaffecter un boîtier.")

    # 🟠 : un changement de `timezone` seul doit aussi déclencher le recalcul — avant ce
    # correctif, seul `clock_offset_seconds` était testé, laissant les médias déjà ingérés
    # dans l'ancien fuseau tant que le décalage numérique ne changeait pas lui aussi.
    recompute_needed = (
        payload.clock_offset_seconds is not None
        and payload.clock_offset_seconds != camera.clock_offset_seconds
    ) or (payload.timezone is not None and payload.timezone != camera.timezone)

    if payload.clock_offset_seconds is not None:
        camera.clock_offset_seconds = payload.clock_offset_seconds
    if payload.timezone is not None:
        camera.timezone = payload.timezone
    if payload.owner_user_id is not None:
        camera.owner_user_id = payload.owner_user_id

    reattach_job_id: int | None = None
    if recompute_needed:
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

    reattached: int | None = None
    if reattach_job_id is not None:
        # 🟠 (§3-E.7 (a)) : sans tick immédiat, le job attend le prochain déclencheur
        # (polling d'un lot, cron) — le critère « le décalage d'horloge corrige
        # rétroactivement » n'était pas démontrable en ligne. `worker_id` unique par
        # requête (§3-E.4, garantie 3, `queue/runner.py`).
        drain(
            SessionLocal,
            f"http-tick-camera-{uuid4().hex[:12]}",
            deadline=datetime.now(UTC) + PATCH_DRAIN_BUDGET,
        )
        job = db.execute(select(Job).where(Job.id == reattach_job_id)).scalar_one_or_none()
        if job is not None and job.status == "done" and job.result:
            reattached = job.result.get("reattached")

    return CameraPatchResponse(
        camera=CameraOut.model_validate(camera),
        reattach_job_id=reattach_job_id,
        reattached=reattached,
    )
