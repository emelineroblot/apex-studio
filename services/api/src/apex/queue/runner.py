"""`drain()` — moteur de drainage de la file (§3-E.2, §3-E.5, §3-E.7 du plan).

Un seul module, deux pilotes (§3-E.7) :
- `apex.cli worker --loop` : boucle locale, appelle `drain()` en rafale et dort 500 ms
  quand la file est vide (voir `apex/cli.py`) ;
- `POST /jobs/tick` (à câbler au lot « stockage/pipeline » suivant) : appelle `drain()`
  une fois avec un budget de temps borné (serverless, `maxDuration=300`).

Vide de logique métier : le registre (`queue.registry`) ne contient encore aucun handler
à ce stade du jalon — un job réclamé ici échoue donc systématiquement avec
`status='failed'` et un message explicite (« kind inconnu »), conformément à §3-E.3
(« jamais de silence »). Les handlers réels arrivent aux lots suivants.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apex.models.job import Job
from apex.queue.claim import claim_batch, reap_stale
from apex.queue.registry import JobContext, get_handler

# Backoff des échecs récupérables (§3-E.2) : 5 s, 30 s, 120 s, puis `dead` au-delà de
# `max_attempts`. Indexé par `attempts` (1 = première tentative déjà consommée par
# `claim_batch`, qui incrémente avant traitement).
BACKOFF_SCHEDULE_SECONDS = (5, 30, 120)

DEFAULT_BATCH_SIZE = 10


@dataclass(slots=True)
class DrainResult:
    """Reflète le contrat `TickResponse` (`schemas/job.py`) : `claimed/done/failed/remaining`."""

    claimed: int = 0
    done: int = 0
    failed: int = 0
    dead: int = 0
    requeued: int = 0
    reaped: int = 0
    remaining: int = 0
    errors: list[str] = field(default_factory=list)

    def as_tick_response(self) -> dict[str, int]:
        """`failed` du contrat d'API regroupe les échecs terminaux : `failed` + `dead`."""
        return {
            "claimed": self.claimed,
            "done": self.done,
            "failed": self.failed + self.dead,
            "remaining": self.remaining,
        }


def _backoff_seconds(attempts: int) -> int:
    index = min(max(attempts, 1), len(BACKOFF_SCHEDULE_SECONDS)) - 1
    return BACKOFF_SCHEDULE_SECONDS[index]


def _count_remaining(session: Session) -> int:
    stmt = select(func.count()).select_from(Job).where(Job.status == "pending")
    return int(session.execute(stmt).scalar_one())


def _make_heartbeat(session: Session, job: Job) -> Callable[[], None]:
    """`ctx.heartbeat()` — à appeler toutes les ~10 s dans les handlers longs (§3-E.5)."""

    def _heartbeat() -> None:
        job.heartbeat_at = datetime.now(UTC)
        session.commit()

    return _heartbeat


def _process_one(session: Session, job: Job, worker_id: str, result: DrainResult) -> None:
    spec = get_handler(job.kind)
    if spec is None:
        job.status = "failed"
        job.last_error = f"kind de job inconnu : « {job.kind} » (aucun handler enregistré)"
        session.commit()
        result.failed += 1
        result.errors.append(job.last_error)
        return

    ctx = JobContext(
        job=job, session=session, worker_id=worker_id, heartbeat=_make_heartbeat(session, job)
    )
    try:
        job_result = spec.func(ctx)
    except Exception as exc:  # noqa: BLE001 — capture volontairement large : un handler
        # ne doit jamais planter le worker, quelle que soit l'erreur.
        message = f"{type(exc).__name__}: {exc}"
        # Un handler qui lève après un `flush()` en échec (ex. contrainte DB) laisse la
        # session en « pending rollback » : tout `commit()` ultérieur lève à son tour et
        # crashe le worker au lieu de consigner l'échec — reproduit en conditions réelles
        # (`NumericValueOutOfRange` sur un `flush()` intermédiaire). Rollback explicite
        # avant de rouvrir une transaction propre, puis on ré-attache `job` (le rollback
        # expire les instances de la session).
        session.rollback()
        refreshed = session.get(Job, job.id)
        if refreshed is None:
            result.errors.append(message)
            return
        job = refreshed
        if job.attempts >= job.max_attempts:
            job.status = "dead"
            job.last_error = message
            session.commit()
            result.dead += 1
        else:
            job.status = "pending"
            job.run_at = datetime.now(UTC) + timedelta(seconds=_backoff_seconds(job.attempts))
            job.last_error = message
            job.locked_by = None
            job.locked_at = None
            job.heartbeat_at = None
            session.commit()
            result.requeued += 1
        result.errors.append(message)
        return

    job.status = "done"
    job.result = job_result
    job.locked_by = None
    job.heartbeat_at = None
    session.commit()
    result.done += 1


def drain(
    session_factory: Callable[[], Session],
    worker_id: str,
    *,
    deadline: datetime | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> DrainResult:
    """Draine la file jusqu'à épuisement ou `deadline` (§3-E.7) — jamais indéfiniment.

    `deadline=None` : draine jusqu'à épuisement de la file puis s'arrête (usage : un
    tick « once »). Ne poll **jamais** en boucle infinie ici — c'est le pilote CLI
    (`--loop`) qui répète les appels avec un sommeil à vide, jamais ce module.
    """
    session = session_factory()
    result = DrainResult()
    try:
        result.reaped = reap_stale(session)

        while True:
            if deadline is not None and datetime.now(UTC) >= deadline:
                break

            batch = claim_batch(session, worker_id, batch_size)
            if not batch:
                break

            result.claimed += len(batch)
            for job in batch:
                if deadline is not None and datetime.now(UTC) >= deadline:
                    # Budget de temps épuisé en cours de lot : le job reste `running`,
                    # `reap_stale` le récupérera au prochain tick si le worker ne
                    # revient pas à temps (§3-E.5) — jamais de perte, jamais de silence.
                    break
                _process_one(session, job, worker_id, result)

        result.remaining = _count_remaining(session)
        return result
    finally:
        session.close()
