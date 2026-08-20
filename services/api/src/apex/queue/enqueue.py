"""Enqueue transactionnel (§3-E.4.2 du plan).

`enqueue()` ne committe jamais lui-même : il doit être appelé **dans la même
transaction** que l'écriture métier qui le justifie (ex. `INSERT media` + enqueue
`ingest_media`, §3-F.4.1). C'est l'appelant qui committe. L'anti-doublon repose sur
l'index unique partiel `job_dedupe_idx` : `INSERT ... ON CONFLICT DO NOTHING`, donc un
rejeu avec le même `dedupe_key` sur un job encore vivant (`pending`/`running`) est un
no-op silencieux — pas une exception.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from apex.models.job import Job

# Doit correspondre **exactement** au prédicat de l'index unique partiel `job_dedupe_idx`
# (`models/job.py`) : PostgreSQL n'infère une cible `ON CONFLICT` sur un index partiel que
# si le `WHERE` de la clause reproduit celui de l'index — sinon `InvalidColumnReference`
# (« there is no unique or exclusion constraint matching the ON CONFLICT specification »),
# reproduit en conditions réelles lors du premier upload transactionnel.
_DEDUPE_INDEX_WHERE = text("dedupe_key IS NOT NULL AND status IN ('pending','running')")


def enqueue(
    session: Session,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    dedupe_key: str | None = None,
    priority: int = 100,
    run_at: datetime | None = None,
    max_attempts: int = 3,
) -> int | None:
    """Insère un job. Renvoie son `id`, ou `None` si un doublon vivant existait déjà.

    Le flush est explicite (`session.flush()`) pour que l'`id` soit disponible avant le
    `commit()` de l'appelant, sans committer à sa place.
    """
    values: dict[str, Any] = {
        "kind": kind,
        "payload": payload or {},
        "dedupe_key": dedupe_key,
        "priority": priority,
        "max_attempts": max_attempts,
    }
    if run_at is not None:
        values["run_at"] = run_at

    if dedupe_key is None:
        job = Job(**values)
        session.add(job)
        session.flush()
        return job.id

    # Doublon vivant possible : passage par un INSERT ... ON CONFLICT DO NOTHING,
    # l'index unique partiel `job_dedupe_idx` ne couvrant que pending/running.
    stmt = (
        pg_insert(Job)
        .values(**values)
        .on_conflict_do_nothing(
            index_elements=["kind", "dedupe_key"], index_where=_DEDUPE_INDEX_WHERE
        )
        .returning(Job.id)
    )
    inserted_id = session.execute(stmt).scalar_one_or_none()
    if inserted_id is not None:
        return int(inserted_id)

    # Rien inséré : soit un doublon vivant existe déjà, soit une coïncidence de conflit
    # sur un autre index — dans notre cas seul `job_dedupe_idx` peut jouer ce rôle.
    return None


def enqueue_unique_pending(session: Session, kind: str, dedupe_key: str) -> int | None:
    """Renvoie l'id du job `pending`/`running` déjà vivant pour ce `(kind, dedupe_key)`.

    Utilitaire de lecture — pratique pour exposer l'id existant à l'appelant (ex.
    `PATCH /cameras/{id}` veut renvoyer `reattach_job_id` même quand il réutilise un job
    déjà en file).
    """
    stmt = select(Job.id).where(
        Job.kind == kind,
        Job.dedupe_key == dedupe_key,
        Job.status.in_(("pending", "running")),
    )
    result = session.execute(stmt).scalar_one_or_none()
    return int(result) if result is not None else None
