"""Handler `ocr_media` (§3-E.3, §3-J.3) — **le seul job du projet qui appelle un modèle**.

Il fait exactement trois choses, dans cet ordre :

1. lire l'**aperçu 1600 px** (pas le HD : 4× plus rapide pour une précision équivalente à
   cette taille de texte, §3-J.3 étape 1) ;
2. demander au moteur quels textes il voit — l'unique appel probabiliste ;
3. **tout le reste en déterministe** : filtrage géométrique, normalisation, score,
   persistance des candidats bruts, puis projection (`classify.project_media`).

L'OCR a son propre job, séparé de `ingest_media` (§3-F.1, Option 2 retenue) : il est plus
coûteux, échoue différemment, et doit être relançable seul.

**Idempotence** (§3-E.6) : avant d'insérer, on supprime les candidats de la **même**
`engine_version` pour ce média — sauf ceux déjà arbitrés par un humain
(`accepted`/`rejected`), qui sont préservés. Rejouer le job converge donc vers le même
état, sans jamais écraser une décision humaine ni empiler les doublons.

**Le seul job du projet qui ne tourne pas partout** (`requires=(OCR_ENGINE,)`) : la fonction
Vercel n'embarque pas le moteur (extra `ocr`, ~322 Mo, au-delà du plafond de 250 Mo). Un
pilote sans moteur ne réclame pas ce job — il le laisse `pending` pour le worker qui l'a,
plutôt que de le faire échouer trois fois puis mourir (`queue/capabilities.py`).

**Un échec d'OCR ne quarantaine jamais un média.** Le fichier va très bien ; c'est la
lecture qui n'a pas abouti. Le média reste `shooting_attached` et un `pipeline_event`
motivé est écrit — le pipeline ne perd rien, il s'abstient (`AGENTS.md`, « l'IA propose »).
"""

from __future__ import annotations

import io
import time
from typing import Any

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from apex.models.job import Job
from apex.models.media import Media, PipelineEvent
from apex.models.search import MediaOcrCandidate
from apex.pipeline.ocr import classify
from apex.pipeline.ocr.engine import get_engine
from apex.pipeline.ocr.scoring import extract_readings
from apex.queue.capabilities import OCR_ENGINE
from apex.queue.registry import JobContext, handler
from apex.services.ocr_settings import load_ocr_settings
from apex.services.search_projection import project_media
from apex.services.storage import ObjectNotFoundError, get_storage_client

#: Taille maximale d'un aperçu lu en mémoire — l'aperçu WebP 1600 px pèse ~200 Ko.
#: Garde-fou : au-delà, on refuse plutôt que de gonfler le worker.
MAX_PREVIEW_BYTES = 32 * 1024 * 1024


def _event(
    session: Session,
    media: Media,
    *,
    job_id: int | None,
    status: str,
    duration_ms: int,
    message: str | None,
) -> None:
    session.add(
        PipelineEvent(
            media_id=media.id,
            batch_id=media.batch_id,
            job_id=job_id,
            step="ocr",
            status=status,
            duration_ms=duration_ms,
            message=message,
        )
    )


def _on_dead(session: Session, job: Job) -> None:
    """§3-E.5 : un job mort doit laisser une trace métier lisible — ici un `pipeline_event`.

    Volontairement **pas** de quarantaine : le média est intact, c'est sa lecture qui a
    échoué. Il reste dans son bac normal, simplement sans candidat OCR.
    """
    media_id = job.payload.get("media_id")
    if media_id is None:
        return
    media = session.get(Media, media_id)
    if media is None:
        return
    _event(
        session,
        media,
        job_id=job.id,
        status="failed",
        duration_ms=0,
        message=f"OCR abandonné après épuisement des tentatives : {job.last_error}",
    )


def _load_preview(media: Media) -> Image.Image | None:
    """Aperçu 1600 px, sinon repli sur le HD. `None` si aucun dérivé n'est disponible."""
    key = media.storage_key_preview or media.storage_key_hd
    if key is None:
        return None
    storage = get_storage_client()
    body = storage.open_stream(key)
    if body.content_length is not None and body.content_length > MAX_PREVIEW_BYTES:
        raise ValueError(f"aperçu anormalement volumineux ({body.content_length} octets)")
    data = b"".join(body.chunks)
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


@handler("ocr_media", max_attempts=3, on_dead=_on_dead, requires=(OCR_ENGINE,))
def handle_ocr_media(ctx: JobContext) -> dict[str, Any]:
    media_id = ctx.job.payload.get("media_id")
    if media_id is None:
        raise ValueError("payload invalide : « media_id » manquant.")

    session = ctx.session
    media = session.get(Media, media_id)
    if media is None:
        raise ValueError(f"media_id={media_id} introuvable — ligne manquante en base.")

    # --- Portée : ce qu'on ne lit pas, et pourquoi -------------------------------------
    if media.ingest_status != "ingested":
        return {"media_id": media_id, "skipped": f"ingest_status={media.ingest_status}"}
    if media.duplicate_of_media_id is not None:
        # Un doublon partage les dérivés de son maître : le lire une seconde fois
        # produirait exactement les mêmes candidats pour un coût identique.
        return {"media_id": media_id, "skipped": "duplicate"}
    if media.shooting_id is None:
        # Sans shooting, aucune table d'engagements : un numéro lu ne pourrait être ni
        # rattaché ni déclaré incohérent. On ne dépense pas d'inférence pour rien.
        return {"media_id": media_id, "skipped": "no_shooting"}

    ocr_settings = load_ocr_settings(session)
    started = time.monotonic()

    try:
        image = _load_preview(media)
    except ObjectNotFoundError as exc:
        _event(
            session,
            media,
            job_id=ctx.job.id,
            status="failed",
            duration_ms=int((time.monotonic() - started) * 1000),
            message=f"aperçu introuvable dans le stockage : {exc}",
        )
        return {"media_id": media_id, "skipped": "preview_missing"}

    if image is None:
        _event(
            session,
            media,
            job_id=ctx.job.id,
            status="failed",
            duration_ms=int((time.monotonic() - started) * 1000),
            message="aucun dérivé disponible pour la lecture OCR",
        )
        return {"media_id": media_id, "skipped": "no_derivative"}

    # --- Orchestration : l'unique appel au modèle --------------------------------------
    ctx.heartbeat()  # l'inférence dure ~1 s : on rafraîchit avant, pas pendant.
    engine = get_engine()
    boxes = engine.read(image)

    # --- Exécution : plus une seule décision probabiliste au-delà de cette ligne -------
    readings = extract_readings(
        boxes,
        image_width=image.width,
        image_height=image.height,
        min_box_area_ratio=ocr_settings.min_box_area_ratio,
        max_box_area_ratio=ocr_settings.max_box_area_ratio,
        top_margin_ratio=ocr_settings.top_margin_ratio,
    )

    _purge_previous_candidates(session, media_id, engine.version)
    for reading in readings:
        session.add(
            MediaOcrCandidate(
                media_id=media_id,
                raw_text=reading.raw_text,
                normalized_number=reading.normalized_number,
                confidence=reading.score,
                bbox=reading.bbox,
                engine_version=engine.version,
                # Résolution provisoire : `project_media` ci-dessous tranche pour de bon.
                # Aucun candidat n'est jamais persisté sans passer par la classification.
                resolution=classify.RESOLUTION_ABSTAIN,
            )
        )
    session.flush()

    projection = classify.project_media(session, media, ocr_settings)
    # L'OCR peut faire passer `attachment_status` de `shooting_attached` à
    # `engagement_attached`/`pending_review`/`inconsistent` — la projection de recherche
    # doit refléter la nouvelle valeur, pas celle écrite à l'ingestion (§3-K).
    project_media(session, media_id)
    duration_ms = int((time.monotonic() - started) * 1000)
    _event(
        session,
        media,
        job_id=ctx.job.id,
        status="ok",
        duration_ms=duration_ms,
        message=(
            f"{len(boxes)} texte(s) détecté(s), {len(readings)} numéro(s) retenu(s) — "
            f"{projection.counts}"
        ),
    )

    return {
        "media_id": media_id,
        "engine_version": engine.version,
        "boxes": len(boxes),
        "candidates": len(readings),
        "attachment_status": media.attachment_status,
        "resolutions": projection.counts,
    }


def _purge_previous_candidates(session: Session, media_id: int, engine_version: str) -> None:
    """Idempotence (§3-E.6) : efface les candidats du même moteur, **jamais** les arbitrages.

    Suppression ligne à ligne plutôt qu'un `DELETE` en masse : les objets déjà chargés dans
    l'identity map de la session (par une projection antérieure dans la même transaction)
    doivent disparaître aussi, sinon un `flush()` ultérieur les ressusciterait.
    """
    stale = session.execute(
        select(MediaOcrCandidate).where(
            MediaOcrCandidate.media_id == media_id,
            MediaOcrCandidate.engine_version == engine_version,
            MediaOcrCandidate.resolution.not_in(classify.HUMAN_RESOLUTIONS),
        )
    ).scalars()
    for candidate in stale:
        session.delete(candidate)
    session.flush()
