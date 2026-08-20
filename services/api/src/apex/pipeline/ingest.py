"""Orchestrateur de `ingest_media` (§3-F.1) — enchaîne les étapes déterministes, un
`pipeline_event` par étape. **Ne lève jamais** : toute erreur inattendue se traduit en
quarantaine motivée (`ingest_failed`), jamais en exception remontée au worker (conforme à
`.claude/instructions/worker-queue.instructions.md`, « pipeline d'ingestion »). Les seules
exceptions qui peuvent remonter sont des pannes d'infrastructure authentiques (base de
données, stockage injoignable) — elles doivent faire échouer/retenter le *job*, pas être
maquillées en quarantaine.
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from PIL import Image
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from apex.models.media import Media, PipelineEvent
from apex.pipeline import attach_time, derivatives, hashing, integrity, phash
from apex.pipeline import exif as exif_mod
from apex.services.storage import (
    ObjectNotFoundError,
    StorageClient,
    StorageError,
    content_addressed_key,
    incoming_key,
)

DERIVATIVE_HD_EXT = "jpg"
DERIVATIVE_WEBP_EXT = "webp"

# §3-F.2 : motif `exif_inconsistent` — date de déclenchement dans le futur ou antérieure à
# 2000. `EXIF_FUTURE_TOLERANCE` absorbe un décalage d'horloge raisonnable (boîtier mal
# réglé) sans pour autant laisser passer une date manifestement aberrante.
EXIF_MIN_YEAR = 2000
EXIF_FUTURE_TOLERANCE = timedelta(days=1)

# Pannes d'infrastructure authentiques (§module docstring) : jamais maquillées en
# quarantaine, elles doivent faire échouer/retenter le *job* — revue J1, 🟠
# (« toute panne d'infrastructure devient une quarantaine terminale »). `ObjectNotFoundError`
# est un sous-type de `StorageError` mais reste, lui, une erreur de **contenu** (le fichier
# attendu n'existe vraiment pas) : géré séparément, avant ce tuple, dans `run_ingest_media`.
_INFRASTRUCTURE_ERRORS: tuple[type[Exception], ...] = (StorageError, DBAPIError)


def _shot_at_exif_is_inconsistent(shot_at_exif: datetime | None) -> bool:
    if shot_at_exif is None:
        return False
    if shot_at_exif.year < EXIF_MIN_YEAR:
        return True
    now_naive = datetime.now(UTC).replace(tzinfo=None)
    return shot_at_exif > now_naive + EXIF_FUTURE_TOLERANCE


@dataclass(slots=True)
class IngestOutcome:
    media_id: int
    ingest_status: str
    attachment_status: str
    quarantine_reason: str | None
    duplicate_of_media_id: int | None


def _write_event(
    session: Session,
    *,
    media_id: int | None,
    batch_id: int | None,
    job_id: int | None,
    step: str,
    status: str,
    duration_ms: int,
    message: str | None,
) -> None:
    session.add(
        PipelineEvent(
            media_id=media_id,
            batch_id=batch_id,
            job_id=job_id,
            step=step,
            status=status,
            duration_ms=duration_ms,
            message=message,
        )
    )


def _quarantine(media: Media, reason: str, detail: dict[str, Any]) -> None:
    media.ingest_status = "quarantined"
    media.quarantine_reason = reason
    media.quarantine_detail = detail
    media.attachment_status = "unattached"


def run_ingest_media(
    session: Session,
    media: Media,
    storage: StorageClient,
    *,
    job_id: int | None,
    studio_name: str,
) -> IngestOutcome:
    media.ingest_status = "processing"
    session.flush()

    def _step(step: str, fn: Any) -> Any:
        started = time.monotonic()
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001 — toute erreur inattendue devient quarantaine
            duration = int((time.monotonic() - started) * 1000)
            _write_event(
                session,
                media_id=media.id,
                batch_id=media.batch_id,
                job_id=job_id,
                step=step,
                status="failed",
                duration_ms=duration,
                message=f"{type(exc).__name__}: {exc}",
            )
            raise _StepFailed(step, exc) from exc
        duration = int((time.monotonic() - started) * 1000)
        _write_event(
            session,
            media_id=media.id,
            batch_id=media.batch_id,
            job_id=job_id,
            step=step,
            status="ok",
            duration_ms=duration,
            message=None,
        )
        return result

    try:
        # 1. fetch — lecture en flux depuis `incoming/…` (§3-F.1).
        key = incoming_key(media.batch_id, media.idempotency_key)

        def _fetch() -> bytes:
            body = storage.open_stream(key)
            return b"".join(body.chunks)

        data: bytes = _step("fetch", _fetch)

        # 2. integrity — quarantaine motivée si le fichier est mauvais, fin de chaîne.
        result = _step("integrity", lambda: integrity.check_integrity(data))
        if not result.ok:
            _write_event(
                session,
                media_id=media.id,
                batch_id=media.batch_id,
                job_id=job_id,
                step="integrity",
                status="quarantined",
                duration_ms=0,
                message=result.reason,
            )
            _quarantine(media, result.reason or "ingest_failed", result.detail)
            if result.width is not None:
                media.width = result.width
            if result.height is not None:
                media.height = result.height
            if result.mime is not None:
                media.mime = result.mime
            session.flush()
            return IngestOutcome(
                media_id=media.id,
                ingest_status=media.ingest_status,
                attachment_status=media.attachment_status,
                quarantine_reason=media.quarantine_reason,
                duplicate_of_media_id=None,
            )

        media.width = result.width
        media.height = result.height
        media.mime = result.mime
        media.byte_size = len(data)

        # 3. hash — BLAKE2b-256 ; si déjà connu, doublon, fin de chaîne (§3-G.1).
        content_hash: bytes = _step("hash", lambda: hashing.hash_bytes(data))
        media.content_hash = content_hash
        content_hash_hex = content_hash.hex()

        # Un troisième (ou Nième) exemplaire du même contenu doit pointer vers le **maître**
        # d'origine, jamais vers un doublon intermédiaire — sinon deux médias partageant le
        # même hash (le maître *et* un doublon déjà résolu, tous deux `ingest_status=
        # 'ingested'`) font lever `MultipleResultsFound` (reproduit en conditions réelles :
        # 3ᵉ upload identique). `duplicate_of_media_id IS NULL` restreint aux vrais maîtres.
        master = session.execute(
            select(Media)
            .where(
                Media.content_hash == content_hash,
                Media.id != media.id,
                Media.ingest_status == "ingested",
                Media.duplicate_of_media_id.is_(None),
            )
            .order_by(Media.id)
            .limit(1)
        ).scalar_one_or_none()

        if master is not None:
            media.duplicate_of_media_id = master.id
            media.storage_key_hd = content_addressed_key("hd", content_hash_hex, DERIVATIVE_HD_EXT)
            media.storage_key_preview = content_addressed_key(
                "preview", content_hash_hex, DERIVATIVE_WEBP_EXT
            )
            media.storage_key_thumb = content_addressed_key(
                "thumb", content_hash_hex, DERIVATIVE_WEBP_EXT
            )
            media.shot_at_exif = master.shot_at_exif
            media.shot_at = master.shot_at
            media.camera_id = master.camera_id
            media.ingest_status = "ingested"
            # Revue J1 (🟠) : avant ce correctif, un doublon atterrissait systématiquement
            # dans le bac « à rattacher » (`attachment_status="unattached"`) sans motif
            # lisible — l'humain n'avait aucune indication que ce média n'était pas
            # réellement orphelin. On mirore l'état de rattachement du maître au moment du
            # dédoublonnage (le maître a déjà traversé tout le pipeline, y compris
            # `attach_time`, avant qu'un doublon ne puisse être détecté) : cohérent et
            # motivé, sans jamais rendre le doublon éditable indépendamment (`GET /media`
            # l'exclut par défaut, `routers/media.py`).
            media.attachment_status = master.attachment_status
            media.attachment_source = master.attachment_source
            media.attachment_detail = master.attachment_detail
            media.shooting_id = master.shooting_id
            _write_event(
                session,
                media_id=media.id,
                batch_id=media.batch_id,
                job_id=job_id,
                step="duplicate",
                status="ok",
                duration_ms=0,
                message=f"doublon de media_id={master.id}",
            )
            session.flush()
            return IngestOutcome(
                media_id=media.id,
                ingest_status=media.ingest_status,
                attachment_status=media.attachment_status,
                quarantine_reason=None,
                duplicate_of_media_id=master.id,
            )

        # 4. exif — tolérant, jamais d'exception (§3-F.1).
        exif_data = _step("exif", lambda: exif_mod.extract_exif(data))

        # §3-F.2 — motif `exif_inconsistent` (revue J1, 🟠 : jamais produit avant ce
        # correctif). Fin de chaîne, comme les autres quarantaines : une date aberrante ne
        # doit pas empêcher de savoir qu'un doublon éventuel existe (le hash est déjà posé
        # ci-dessus), mais elle ne doit pas non plus être rattachée à un shooting.
        if _shot_at_exif_is_inconsistent(exif_data.shot_at_exif):
            _write_event(
                session,
                media_id=media.id,
                batch_id=media.batch_id,
                job_id=job_id,
                step="exif",
                status="quarantined",
                duration_ms=0,
                message="exif_inconsistent",
            )
            assert exif_data.shot_at_exif is not None  # narrows for mypy — guard above
            _quarantine(
                media,
                "exif_inconsistent",
                {"shot_at_exif": exif_data.shot_at_exif.isoformat()},
            )
            session.flush()
            return IngestOutcome(
                media_id=media.id,
                ingest_status=media.ingest_status,
                attachment_status=media.attachment_status,
                quarantine_reason=media.quarantine_reason,
                duplicate_of_media_id=None,
            )

        # Revue J1 (🔴 n°1) : `resolve_camera` (I/O base) et `compute_shot_at` (peut lever
        # `ValueError` sur un fuseau invalide, ex. `ZoneInfo("")` — cf. `pipeline/exif.py`)
        # doivent passer par `_step`, comme toute autre étape : le contrat de tête de
        # module (« ne lève jamais ») était rompu tant qu'elles s'exécutaient hors de son
        # filet.
        camera = _step("resolve_camera", lambda: exif_mod.resolve_camera(session, exif_data))
        shot_at = _step(
            "compute_shot_at", lambda: exif_mod.compute_shot_at(exif_data.shot_at_exif, camera)
        )

        media.shot_at_exif = exif_data.shot_at_exif
        media.shot_at = shot_at
        media.camera_id = camera.id if camera is not None else None
        media.lens_model = exif_data.lens_model
        media.iso = exif_data.iso
        media.shutter_speed_sec = exif_data.shutter_speed_sec
        media.shutter_speed_label = exif_data.shutter_speed_label
        media.aperture = exif_data.aperture
        media.focal_length = exif_data.focal_length
        media.gps_lat = exif_data.gps_lat
        media.gps_lon = exif_data.gps_lon
        media.exif_raw = exif_data.raw

        # 5. derivatives — vignette + aperçu filigrané (§3-H.3), HD stocké tel quel.
        def _derivatives() -> tuple[bytes, bytes, Image.Image]:
            with Image.open(io.BytesIO(data)) as src:
                src.load()
                thumb_bytes = derivatives.build_thumb(src)
                preview_bytes = derivatives.build_watermarked_preview(src, studio_name)
                thumb_img = Image.open(io.BytesIO(thumb_bytes)).convert("L")
                thumb_img.load()
            return thumb_bytes, preview_bytes, thumb_img

        thumb_bytes, preview_bytes, thumb_gray_img = _step("derivatives", _derivatives)

        hd_key = content_addressed_key("hd", content_hash_hex, DERIVATIVE_HD_EXT)
        preview_key = content_addressed_key("preview", content_hash_hex, DERIVATIVE_WEBP_EXT)
        thumb_key = content_addressed_key("thumb", content_hash_hex, DERIVATIVE_WEBP_EXT)

        # Revue J1 (🔴 n°1) : les trois écritures de stockage doivent passer par `_step` —
        # une panne de stockage (quota, R2 injoignable) au milieu des trois écritures ne
        # doit jamais s'échapper du filet et crasher le worker.
        def _store() -> None:
            storage.put_bytes(hd_key, data, content_type="image/jpeg")
            storage.put_bytes(preview_key, preview_bytes, content_type="image/webp")
            storage.put_bytes(thumb_key, thumb_bytes, content_type="image/webp")

        _step("store", _store)
        media.storage_key_hd = hd_key
        media.storage_key_preview = preview_key
        media.storage_key_thumb = thumb_key

        # 6. attach_time — rattachement au shooting par fenêtre temporelle (§3-F.3).
        _step("attach_time", lambda: attach_time.attach_media_by_time(session, media))

        # 7. phash + sharpness — sur la vignette, pas le HD (§3-G.2, §3-G.3).
        def _phash_sharpness() -> tuple[int, float]:
            import numpy as np

            gray = np.asarray(thumb_gray_img, dtype=np.float64)
            return phash.compute_phash(gray), phash.compute_sharpness(gray)

        phash_value, sharpness_value = _step("phash", _phash_sharpness)
        media.phash = phash.to_signed_bigint(phash_value)
        media.sharpness = sharpness_value

        media.ingest_status = "ingested"
        session.flush()
        return IngestOutcome(
            media_id=media.id,
            ingest_status=media.ingest_status,
            attachment_status=media.attachment_status,
            quarantine_reason=None,
            duplicate_of_media_id=None,
        )

    except _StepFailed as failed:
        # Revue J1 (🟠) : avant ce correctif, les deux branches faisaient la même chose —
        # **toute** panne d'infrastructure (R2 injoignable, base de données coupée en plein
        # `flush()`) devenait une quarantaine terminale au lieu d'un retry. Seule une
        # erreur de **contenu** doit quarantiner le média ; une panne d'infrastructure
        # authentique doit au contraire s'échapper ici pour que le worker (`runner.py`)
        # la traite comme un échec de *job* récupérable (requeue avec backoff).
        if isinstance(failed.original, ObjectNotFoundError):
            # Fichier attendu absent du stockage : jamais silencieux, jamais perdu — la
            # ligne `media` existe déjà (garantie transactionnelle §3-F.4.1), on la
            # quarantaine plutôt que de la laisser en `uploaded`/`processing` pour toujours.
            # Sous-type de `StorageError` mais traité en premier : contrairement à une
            # panne réseau/quota, un objet durablement absent ne se résoudra pas tout seul
            # au prochain essai.
            _quarantine(
                media, "ingest_failed", {"step": failed.step, "error": str(failed.original)}
            )
        elif isinstance(failed.original, _INFRASTRUCTURE_ERRORS):
            raise failed.original from failed
        else:
            _quarantine(
                media, "ingest_failed", {"step": failed.step, "error": str(failed.original)}
            )
        session.flush()
        return IngestOutcome(
            media_id=media.id,
            ingest_status=media.ingest_status,
            attachment_status=media.attachment_status,
            quarantine_reason=media.quarantine_reason,
            duplicate_of_media_id=None,
        )


class _StepFailed(Exception):
    def __init__(self, step: str, original: Exception) -> None:
        super().__init__(f"étape « {step} » en échec : {original}")
        self.step = step
        self.original = original
