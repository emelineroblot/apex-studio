"""Preuve du correctif revue J1 (🔴 n°2) : `drain(deadline=...)` ne doit **jamais**
abandonner un job réclamé-mais-non-exécuté en `running` — et ne doit jamais lui faire
consommer une tentative. Avant le correctif, `queue/runner.py` sortait de la boucle en
laissant les jobs restants du lot `running`, `attempts` déjà incrémenté par `claim_batch` :
trois cycles de polling identiques suffisaient à quarantiner des médias jamais ouverts.
"""

from __future__ import annotations

import datetime
import time

from sqlalchemy import select

from apex.db import SessionLocal
from apex.models.job import Job
from apex.queue.enqueue import enqueue
from apex.queue.registry import JobContext, handler
from apex.queue.runner import drain

SLOW_KIND = "test_drain_deadline_probe"
JOB_DURATION_SECONDS = 0.2


@handler(SLOW_KIND, max_attempts=3)
def _slow_handler(ctx: JobContext) -> dict[str, bool]:
    time.sleep(JOB_DURATION_SECONDS)
    return {"ok": True}


def test_deadline_releases_unclaimed_jobs_without_consuming_an_attempt(db_session) -> None:
    job_ids = [
        enqueue(db_session, SLOW_KIND, {"i": i}, dedupe_key=f"drain-deadline:{i}") for i in range(3)
    ]
    db_session.commit()

    # Budget large pour ~1,5 job (200 ms/job) : le premier job (et souvent le second)
    # s'exécute, le budget expire ensuite en plein lot — exactement le scénario du
    # bloquant n°2 (`GET_BATCH_DRAIN_BUDGET` trop court face à `batch_size`).
    deadline = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
        seconds=JOB_DURATION_SECONDS * 1.5
    )
    result = drain(SessionLocal, "test-deadline-worker", deadline=deadline, batch_size=3)

    assert result.claimed == 3
    # Au moins un job n'a pas eu le temps d'être traité et a dû être relâché.
    assert result.released >= 1
    assert result.done + result.released == 3

    check_session = SessionLocal()
    try:
        jobs = list(check_session.execute(select(Job).where(Job.id.in_(job_ids))).scalars().all())
    finally:
        check_session.close()

    assert len(jobs) == 3
    # Invariant central du correctif : plus aucun job `running` une fois `drain()` revenu —
    # ni resté bloqué, ni consommé de tentative pour un travail jamais exécuté.
    for job in jobs:
        assert job.status in ("pending", "done"), job.status
        if job.status == "pending":
            assert job.attempts == 0, "une réclamation sans exécution a consommé une tentative"
            assert job.locked_by is None
            assert job.heartbeat_at is None
        else:
            assert job.attempts == 1
