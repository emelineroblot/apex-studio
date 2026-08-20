"""Réclamation atomique et reprise après crash (§3-E.2 et §3-E.5 du plan).

Deux requêtes SQL brutes, chacune une transaction courte et committée immédiatement par
l'appelant (`runner.drain`) — le verrou physique `FOR UPDATE SKIP LOCKED` ne dure que le
temps de la requête, `status='running' AND locked_by=...` jouant ensuite le rôle de
verrou logique pendant tout le traitement (§3-E.2, Option 2 retenue).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import select, text
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from apex.models.job import Job
from apex.queue.registry import get_handler

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
     WHERE status = 'running' AND (heartbeat_at < :stale_before OR heartbeat_at IS NULL)
    RETURNING id, status, kind
    """
)

# Relâche un job réclamé (`claim_batch`) mais jamais exécuté — budget de temps de `drain()`
# épuisé avant d'y arriver (§3-E.2, revue J1 bloquant n°2). Gardé par `locked_by` (§3-E.4,
# garantie 3) : n'agit que si CE worker détient toujours le job. `attempts` est décrémenté
# pour annuler l'incrément fait par `_CLAIM_SQL` — une réclamation sans exécution ne doit
# **jamais** consommer une tentative, sous peine de mettre en quarantaine des médias
# valides jamais ouverts après quelques cycles de polling (scénario détaillé en revue).
_RELEASE_SQL = text(
    """
    UPDATE job
       SET status = 'pending', attempts = GREATEST(attempts - 1, 0), run_at = now(),
           locked_by = NULL, locked_at = NULL, heartbeat_at = NULL, updated_at = now()
     WHERE id = :id AND locked_by = :worker_id AND status = 'running'
    """
)

_HEARTBEAT_SQL = text(
    """
    UPDATE job SET heartbeat_at = now(), updated_at = now()
     WHERE id = :id AND locked_by = :worker_id AND status = 'running'
    """
)


def release_unclaimed(session: Session, jobs: list[Job], worker_id: str) -> int:
    """Relâche des jobs réclamés par `worker_id` mais jamais passés à `_process_one` —
    voir `_RELEASE_SQL`. Renvoie le nombre effectivement relâché (`rowcount` sommé,
    jamais supposé égal à `len(jobs)` : un autre worker a pu entre-temps reprendre l'un
    d'eux via `reap_stale`, auquel cas la garde `locked_by` fait échouer cette ligne-là,
    ce qui est le comportement voulu).
    """
    released = 0
    for job in jobs:
        outcome = cast(
            CursorResult, session.execute(_RELEASE_SQL, {"id": job.id, "worker_id": worker_id})
        )
        released += outcome.rowcount
    session.commit()
    return released


def heartbeat(session: Session, job_id: int, worker_id: str) -> bool:
    """Rafraîchit `heartbeat_at` (§3-E.5) — `True` si ce worker détient toujours le job."""
    outcome = cast(
        CursorResult, session.execute(_HEARTBEAT_SQL, {"id": job_id, "worker_id": worker_id})
    )
    session.commit()
    return bool(outcome.rowcount)


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
    Pour tout job passé à `dead`, dispatche le hook `on_dead` du handler enregistré (s'il
    existe) **dans la même transaction** que la bascule d'état — « aucun job mort ne laisse
    un objet métier dans un état intermédiaire » (§3-E.5). Renvoie le nombre de jobs repris.
    """
    stale_before = datetime.now(UTC) - stale_after
    rows = list(session.execute(_REAP_SQL, {"stale_before": stale_before}))
    reaped = len(rows)
    session.commit()

    for row in rows:
        if row.status != "dead":
            continue
        spec = get_handler(row.kind)
        if spec is None or spec.on_dead is None:
            continue
        job = session.execute(select(Job).where(Job.id == row.id)).scalar_one_or_none()
        if job is None:
            continue
        try:
            spec.on_dead(session, job)
            session.commit()
        except Exception:  # noqa: BLE001 — un hook `on_dead` défaillant ne doit jamais
            # empêcher le reste du drainage ; l'état `dead` du job, déjà committé, reste
            # visible et actionnable manuellement.
            session.rollback()

    return reaped
