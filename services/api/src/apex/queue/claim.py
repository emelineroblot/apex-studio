"""Réclamation atomique et reprise après crash (§3-E.2 et §3-E.5 du plan).

Deux requêtes SQL brutes, chacune une transaction courte et committée immédiatement par
l'appelant (`runner.drain`) — le verrou physique `FOR UPDATE SKIP LOCKED` ne dure que le
temps de la requête, `status='running' AND locked_by=...` jouant ensuite le rôle de
verrou logique pendant tout le traitement (§3-E.2, Option 2 retenue).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from apex.models.job import Job

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult

# Seuil de détection des jobs orphelins : un job `running` sans heartbeat depuis plus
# longtemps que ça est considéré mort (§3-E.5). Volontairement inférieur au
# `maxDuration=300s` des fonctions Vercel — c'est le heartbeat, pas la durée, qui fait foi.
STALE_AFTER = timedelta(minutes=3)

_CLAIM_SQL = text(
    """
    WITH claimed AS (
        SELECT id FROM job
         WHERE status = 'pending' AND run_at <= now()
         ORDER BY priority, run_at, id
         FOR UPDATE SKIP LOCKED
         LIMIT :batch_size
    )
    UPDATE job j
       SET status = 'running', attempts = j.attempts + 1, locked_by = :worker_id,
           locked_at = now(), heartbeat_at = now(), updated_at = now()
      FROM claimed c
     WHERE j.id = c.id
    RETURNING j.id
    """
)

_REAP_SQL = text(
    """
    UPDATE job
       SET status = CASE WHEN attempts >= max_attempts THEN 'dead' ELSE 'pending' END,
           run_at = now(), locked_by = NULL, locked_at = NULL, heartbeat_at = NULL,
           last_error = coalesce(last_error, '') || ' | repris après worker silencieux',
           updated_at = now()
     WHERE status = 'running' AND heartbeat_at < :stale_before
    RETURNING id, status
    """
)


def claim_batch(session: Session, worker_id: str, batch_size: int) -> list[Job]:
    """Réclame jusqu'à `batch_size` jobs `pending` dus, atomiquement. Committe aussitôt."""
    params = {"worker_id": worker_id, "batch_size": batch_size}
    ids = [row[0] for row in session.execute(_CLAIM_SQL, params)]
    session.commit()
    if not ids:
        return []
    jobs = session.execute(select(Job).where(Job.id.in_(ids))).scalars().all()
    # Préserve l'ordre de réclamation (priorité, run_at, id) — perdu par `IN (...)`.
    by_id = {job.id: job for job in jobs}
    return [by_id[i] for i in ids if i in by_id]


def reap_stale(session: Session, *, stale_after: timedelta = STALE_AFTER) -> int:
    """Repasse en `pending` (ou `dead` si épuisé) les jobs `running` orphelins (§3-E.5).

    Committe immédiatement — appelé en tête de chaque `drain()`, avant toute réclamation.
    Renvoie le nombre de jobs repris.
    """
    stale_before = datetime.now(UTC) - stale_after
    result = session.execute(_REAP_SQL, {"stale_before": stale_before})
    # `.rowcount` existe bien à l'exécution (CursorResult, DML) — les stubs `Result[Any]`
    # génériques de SQLAlchemy ne l'exposent pas statiquement.
    reaped = cast("CursorResult[Any]", result).rowcount
    session.commit()
    return reaped
