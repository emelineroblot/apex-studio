"""Handler `ingest_media` (§3-E.3, §3-F du plan) — enveloppe fine autour de
`pipeline.ingest.run_ingest_media` : résout le média et le stockage, appelle le pipeline,
enqueue `finalize_batch` dans la même transaction (§3-E.4.2).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from apex.config import settings
from apex.models.job import Job
from apex.models.media import Media
from apex.pipeline.ingest import run_ingest_media
from apex.queue.enqueue import enqueue
from apex.queue.registry import JobContext, handler
from apex.services.search_projection import project_media
from apex.services.storage import get_storage_client


def _on_dead(session: Session, job: Job) -> None:
    """§3-E.5 : un job `ingest_media` mort (retries épuisés) doit quarantiner son média —
    jamais le laisser en `uploaded`/`processing` indéfiniment.
    """
    media_id = job.payload.get("media_id")
    if media_id is None:
        return
    media = session.get(Media, media_id)
    if media is None or media.ingest_status in ("ingested", "quarantined"):
        return
    media.ingest_status = "quarantined"
    media.quarantine_reason = "ingest_failed"
    media.quarantine_detail = {"reason": "job_dead", "last_error": job.last_error}
    media.attachment_status = "unattached"


@handler("ingest_media", max_attempts=3, on_dead=_on_dead)
def handle_ingest_media(ctx: JobContext) -> dict[str, Any]:
    media_id = ctx.job.payload.get("media_id")
    if media_id is None:
        raise ValueError("payload invalide : « media_id » manquant.")

    media = ctx.session.get(Media, media_id)
    if media is None:
        # Ne devrait jamais arriver (garantie transactionnelle §3-F.4.1) — traité comme un
        # échec non récupérable plutôt qu'un silence.
        raise ValueError(f"media_id={media_id} introuvable — ligne manquante en base.")

    storage = get_storage_client()
    outcome = run_ingest_media(
        ctx.session, media, storage, job_id=ctx.job.id, studio_name=settings.studio_name
    )

    # §3-F.1, étape 8 (« index ») : la ligne `media_search` est écrite ici, quelle que soit
    # l'issue (ingéré, quarantaine, doublon) — un média absent de la projection est un média
    # introuvable en recherche, invariant signalé par l'agent OCR en sortie de son lot.
    project_media(ctx.session, media.id)

    # Enqueue transactionnel (§3-E.4.2) : recalcule les compteurs du lot, regroupe les
    # rafales — un rejeu par média successif est absorbé par le dédoublonnage d'enqueue.
    enqueue(
        ctx.session,
        "finalize_batch",
        {"batch_id": media.batch_id},
        dedupe_key=f"batch:{media.batch_id}",
        priority=120,
    )

    # §3-F.1, étape 9 (J2) : l'OCR a son propre job — plus coûteux, il échoue différemment
    # et doit rester relançable seul. On ne l'enqueue que si le média a rejoint un
    # shooting : sans table d'engagements, un numéro lu ne serait ni rattachable ni
    # déclarable incohérent (voir `handlers/ocr_media.py`).
    if (
        outcome.ingest_status == "ingested"
        and outcome.duplicate_of_media_id is None
        and media.shooting_id is not None
    ):
        enqueue(
            ctx.session,
            "ocr_media",
            {"media_id": media.id},
            dedupe_key=f"ocr:{media.id}",
            priority=110,
        )

    return {
        "media_id": outcome.media_id,
        "ingest_status": outcome.ingest_status,
        "attachment_status": outcome.attachment_status,
        "quarantine_reason": outcome.quarantine_reason,
        "duplicate_of_media_id": outcome.duplicate_of_media_id,
    }
