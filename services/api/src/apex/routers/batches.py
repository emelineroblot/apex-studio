"""Upload par lot — `upload_batch` (§3-F.4). Enqueue transactionnel : impossible d'avoir
un média en base sans job associé.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, File, Header, HTTPException, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apex.config import settings
from apex.db import SessionLocal, get_db
from apex.models.media import Media, PipelineEvent, UploadBatch
from apex.models.shooting import Shooting
from apex.queue.enqueue import enqueue
from apex.queue.runner import drain
from apex.schemas.batch import (
    BatchCloseResponse,
    BatchCreateRequest,
    BatchCreateResponse,
    BatchStatusCounts,
    BatchStatusResponse,
    FileUploadResponse,
    PipelineEventOut,
)
from apex.security import CurrentUser
from apex.services import access
from apex.services.storage import get_storage_client, incoming_key

router = APIRouter(prefix="/batches", tags=["batches"])

TERMINAL_INGEST_STATUSES = ("ingested", "quarantined")
GET_BATCH_DRAIN_BUDGET = timedelta(seconds=1.5)
MAX_EVENTS = 100


def _get_batch_or_404(db: Session, user: CurrentUser, batch_id: int) -> UploadBatch:
    batch = db.execute(select(UploadBatch).where(UploadBatch.id == batch_id)).scalar_one_or_none()
    if batch is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "Lot introuvable.", "detail": None},
        )
    access.assert_can_read_batch(db, user, batch)
    return batch


@router.post("", response_model=BatchCreateResponse, status_code=201, summary="Ouvrir un lot")
def create_batch(
    payload: BatchCreateRequest, user: CurrentUser, db: Session = Depends(get_db)
) -> BatchCreateResponse:
    if payload.shooting_hint_id is not None:
        shooting = db.execute(
            select(Shooting.id).where(Shooting.id == payload.shooting_hint_id)
        ).scalar_one_or_none()
        if shooting is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "invalid_shooting_hint",
                    "message": "Shooting indiqué introuvable.",
                    "detail": None,
                },
            )
    batch = UploadBatch(
        created_by=user.id,
        shooting_hint_id=payload.shooting_hint_id,
        expected_count=payload.expected_count,
        status="open",
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return BatchCreateResponse(
        id=batch.id, status=batch.status, expected_count=batch.expected_count
    )


def _shooting_quota_usage_bytes(db: Session, shooting_id: int) -> int:
    stmt = (
        select(func.coalesce(func.sum(Media.byte_size), 0))
        .select_from(Media)
        .join(UploadBatch, UploadBatch.id == Media.batch_id)
        .where(UploadBatch.shooting_hint_id == shooting_id)
    )
    return int(db.execute(stmt).scalar_one())


@router.post(
    "/{batch_id}/files",
    response_model=FileUploadResponse,
    status_code=201,
    summary="Déposer un fichier dans le lot (upload idempotent)",
)
def upload_file(
    batch_id: int,
    user: CurrentUser,
    response: Response,
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> FileUploadResponse:
    batch = _get_batch_or_404(db, user, batch_id)

    # Idempotence de l'upload (§3-F.4.2) : un rejeu renvoie le même `media_id`, jamais de
    # nouvelle ligne — c'est ce qui sécurise la reprise d'un lot après interruption.
    existing = db.execute(
        select(Media).where(Media.batch_id == batch_id, Media.idempotency_key == idempotency_key)
    ).scalar_one_or_none()
    if existing is not None:
        response.status_code = 200
        return FileUploadResponse(media_id=existing.id, status="uploaded", duplicate=True)

    if batch.status != "open":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "batch_not_open",
                "message": "Ce lot n'accepte plus de nouveaux fichiers.",
                "detail": {"status": batch.status},
            },
        )

    data = file.file.read()

    # Quota (§3-H.3) — vérifié avant chaque PUT. Dépassement : jamais un rejet muet, le
    # média est créé **et** quarantiné, l'API répond 413 avec le motif métier.
    quarantine_reason: str | None = None
    quarantine_detail: dict[str, object] = {}
    if len(data) > settings.max_upload_bytes:
        quarantine_reason = "too_large"
        quarantine_detail = {"byte_size": len(data), "max_upload_bytes": settings.max_upload_bytes}
    elif batch.shooting_hint_id is not None:
        shooting = db.execute(
            select(Shooting).where(Shooting.id == batch.shooting_hint_id)
        ).scalar_one_or_none()
        if shooting is not None:
            used = _shooting_quota_usage_bytes(db, shooting.id)
            if used + len(data) > shooting.quota_bytes:
                quarantine_reason = "quota_exceeded"
                quarantine_detail = {
                    "used_bytes": used,
                    "incoming_bytes": len(data),
                    "quota_bytes": shooting.quota_bytes,
                }

    storage = get_storage_client()
    storage.put_bytes(incoming_key(batch_id, idempotency_key), data)

    media = Media(
        batch_id=batch_id,
        uploaded_by=user.id,
        idempotency_key=idempotency_key,
        original_filename=file.filename or idempotency_key,
        byte_size=len(data),
        ingest_status="quarantined" if quarantine_reason else "uploaded",
        quarantine_reason=quarantine_reason,
        quarantine_detail=quarantine_detail or None,
        attachment_status="unattached",
    )
    db.add(media)
    db.flush()  # id disponible pour l'enqueue, toujours dans la même transaction (§3-F.4.1)

    if quarantine_reason is None:
        enqueue(db, "ingest_media", {"media_id": media.id}, dedupe_key=f"media:{media.id}")

    db.commit()
    db.refresh(media)

    if quarantine_reason == "quota_exceeded":
        raise HTTPException(
            status_code=413,
            detail={
                "code": "quota_exceeded",
                "message": "Le quota de stockage du shooting est dépassé.",
                "detail": {"media_id": media.id, **quarantine_detail},
            },
        )
    if quarantine_reason == "too_large":
        raise HTTPException(
            status_code=413,
            detail={
                "code": "file_too_large",
                "message": "Le fichier dépasse la taille maximale autorisée.",
                "detail": {"media_id": media.id, **quarantine_detail},
            },
        )

    return FileUploadResponse(media_id=media.id, status="uploaded", duplicate=False)


@router.post("/{batch_id}/close", response_model=BatchCloseResponse, summary="Clôturer un lot")
def close_batch(
    batch_id: int, user: CurrentUser, db: Session = Depends(get_db)
) -> BatchCloseResponse:
    batch = _get_batch_or_404(db, user, batch_id)
    if batch.status == "open":
        batch.status = "processing"
        batch.closed_at = datetime.now(UTC)
        db.commit()
        db.refresh(batch)
    return BatchCloseResponse(id=batch.id, status=batch.status)


@router.get(
    "/{batch_id}",
    response_model=BatchStatusResponse,
    summary="Suivi du lot (polling 1 s) — déclenche un tick si la file n'est pas vide",
)
def get_batch(
    batch_id: int, user: CurrentUser, db: Session = Depends(get_db)
) -> BatchStatusResponse:
    batch = _get_batch_or_404(db, user, batch_id)

    if batch.status != "closed":
        # Le polling de l'UI est ce qui fait avancer la file en environnement serverless
        # (§3-E.7, Option 2) — budget de temps court pour ne pas bloquer la requête.
        deadline = datetime.now(UTC) + GET_BATCH_DRAIN_BUDGET
        drain(SessionLocal, "http-poll", deadline=deadline)
        db.expire_all()
        batch = _get_batch_or_404(db, user, batch_id)

    counts_rows = db.execute(
        select(Media.ingest_status, func.count())
        .select_from(Media)
        .where(Media.batch_id == batch_id)
        .group_by(Media.ingest_status)
    ).all()
    counts_map: dict[str, int] = dict(counts_rows)  # type: ignore[arg-type]
    counts = BatchStatusCounts(
        uploaded=counts_map.get("uploaded", 0),
        processing=counts_map.get("processing", 0),
        ingested=counts_map.get("ingested", 0),
        quarantined=counts_map.get("quarantined", 0),
    )
    received_count = sum(counts_map.values())

    attached_count = db.execute(
        select(func.count())
        .select_from(Media)
        .where(
            Media.batch_id == batch_id,
            Media.attachment_status.in_(("shooting_attached", "engagement_attached")),
        )
    ).scalar_one()
    duplicate_count = db.execute(
        select(func.count())
        .select_from(Media)
        .where(Media.batch_id == batch_id, Media.duplicate_of_media_id.is_not(None))
    ).scalar_one()

    terminal_count = counts.ingested + counts.quarantined
    progress = 1.0 if batch.expected_count <= 0 else min(1.0, terminal_count / batch.expected_count)
    missing_count = max(batch.expected_count - received_count, 0)

    events = (
        db.execute(
            select(PipelineEvent)
            .where(PipelineEvent.batch_id == batch_id)
            .order_by(PipelineEvent.created_at.desc())
            .limit(MAX_EVENTS)
        )
        .scalars()
        .all()
    )

    return BatchStatusResponse(
        id=batch.id,
        expected_count=batch.expected_count,
        received_count=received_count,
        counts=counts,
        attached_count=attached_count,
        duplicate_count=duplicate_count,
        progress=progress,
        missing_count=missing_count,
        done=batch.status == "closed",
        events=[PipelineEventOut.model_validate(e) for e in reversed(events)],
    )
