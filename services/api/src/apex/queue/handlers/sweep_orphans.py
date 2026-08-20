"""Handler `sweep_orphans` (§3-F.4.6) — dernier maillon de la chaîne de garanties : tout
objet du préfixe `incoming/` vieux de plus d'une heure sans ligne `media` correspondante
**devient une ligne en quarantaine**, jamais un `DELETE`. « On préfère un bac visible à un
octet perdu. »
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from apex.models.media import Media, UploadBatch
from apex.queue.registry import JobContext, handler
from apex.services.storage import get_storage_client

ORPHAN_AGE_THRESHOLD = timedelta(hours=1)


def _parse_incoming_key(key: str) -> tuple[int, str] | None:
    parts = key.split("/", 2)
    if len(parts) != 3 or parts[0] != "incoming":
        return None
    try:
        batch_id = int(parts[1])
    except ValueError:
        return None
    idempotency_key = parts[2]
    if not idempotency_key:
        return None
    return batch_id, idempotency_key


@handler("sweep_orphans", max_attempts=3)
def handle_sweep_orphans(ctx: JobContext) -> dict[str, Any]:
    session = ctx.session
    storage = get_storage_client()
    now = datetime.now(UTC)

    scanned = 0
    quarantined = 0
    skipped_unresolvable = 0

    for key in storage.list_prefix("incoming/"):
        scanned += 1
        parsed = _parse_incoming_key(key)
        if parsed is None:
            skipped_unresolvable += 1
            continue
        batch_id, idempotency_key = parsed

        already = session.execute(
            select(Media.id).where(
                Media.batch_id == batch_id, Media.idempotency_key == idempotency_key
            )
        ).scalar_one_or_none()
        if already is not None:
            continue  # ligne présente — pas un orphelin, comportement normal (§3-F.4.1)

        last_modified = storage.object_last_modified(key)
        if last_modified is None or now - last_modified < ORPHAN_AGE_THRESHOLD:
            continue  # laisse le temps à un upload en cours de finir sa transaction

        batch = session.get(UploadBatch, batch_id)
        if batch is None:
            # Clé illisible jusqu'au bout (lot inexistant) — cas pathologique, signalé sans
            # bloquer le reste du balayage.
            skipped_unresolvable += 1
            continue

        byte_size = storage.object_size(key) or 0
        orphan = Media(
            batch_id=batch_id,
            uploaded_by=batch.created_by,
            idempotency_key=idempotency_key,
            original_filename=f"(objet orphelin) {idempotency_key}",
            byte_size=byte_size,
            ingest_status="quarantined",
            quarantine_reason="orphan_object",
            quarantine_detail={"storage_key": key, "found_at": now.isoformat()},
            attachment_status="unattached",
        )
        session.add(orphan)
        session.flush()
        quarantined += 1

    return {
        "scanned": scanned,
        "quarantined": quarantined,
        "skipped_unresolvable": skipped_unresolvable,
    }
