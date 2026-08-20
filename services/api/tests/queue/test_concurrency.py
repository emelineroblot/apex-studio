"""Preuve de non-double-traitement (§3-E.4 du plan) — **obligatoire** : 500 jobs, 8
threads workers, chaque handler insère dans `job_execution_log` (`UNIQUE(job_id)`).
Connexions réellement indépendantes (pas de mock, §3-D) — c'est exactement le scénario que
`SELECT ... FOR UPDATE SKIP LOCKED` doit protéger.
"""

from __future__ import annotations

import threading

from sqlalchemy import func, select

from apex.db import SessionLocal
from apex.models.job import Job, JobExecutionLog
from apex.queue.enqueue import enqueue
from apex.queue.registry import JobContext, handler
from apex.queue.runner import drain

TOTAL_JOBS = 500
WORKER_THREADS = 8
PROBE_KIND = "test_concurrency_probe"


@handler(PROBE_KIND, max_attempts=1)
def _probe_handler(ctx: JobContext) -> dict[str, bool]:
    # Si ce job a déjà été réclamé et traité par un autre worker, la contrainte
    # `UNIQUE(job_id)` de `job_execution_log` fait échouer ce second `INSERT` — c'est la
    # preuve recherchée (§3-E.4).
    ctx.session.add(JobExecutionLog(job_id=ctx.job.id, worker_id=ctx.worker_id))
    ctx.session.flush()
    return {"ok": True}


def test_no_double_processing_under_concurrency() -> None:
    seed_session = SessionLocal()
    try:
        for i in range(TOTAL_JOBS):
            enqueue(seed_session, PROBE_KIND, {"i": i}, dedupe_key=f"probe:{i}")
        seed_session.commit()
    finally:
        seed_session.close()

    errors: list[BaseException] = []

    def _run_worker(worker_id: str) -> None:
        try:
            drain(SessionLocal, worker_id, deadline=None, batch_size=10)
        except BaseException as exc:  # noqa: BLE001 — capturé pour remonter dans le thread principal
            errors.append(exc)

    threads = [
        threading.Thread(target=_run_worker, args=(f"worker-{i}",)) for i in range(WORKER_THREADS)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert not errors, f"un ou plusieurs workers ont levé une exception : {errors}"

    check_session = SessionLocal()
    try:
        log_count = check_session.execute(
            select(func.count()).select_from(JobExecutionLog)
        ).scalar_one()
        distinct_job_ids = check_session.execute(
            select(func.count(func.distinct(JobExecutionLog.job_id)))
        ).scalar_one()
        done_count = check_session.execute(
            select(func.count())
            .select_from(Job)
            .where(Job.kind == PROBE_KIND, Job.status == "done")
        ).scalar_one()
        unfinished = check_session.execute(
            select(func.count())
            .select_from(Job)
            .where(Job.kind == PROBE_KIND, Job.status.in_(("pending", "running")))
        ).scalar_one()
    finally:
        check_session.close()

    # Aucune violation d'unicité (sinon un thread aurait levé et été comptabilisé dans
    # `errors` ci-dessus) : chaque job a produit exactement une ligne de log.
    assert log_count == TOTAL_JOBS, f"attendu {TOTAL_JOBS} logs, obtenu {log_count}"
    assert distinct_job_ids == TOTAL_JOBS, "un même job_id a été traité plusieurs fois"
    assert done_count == TOTAL_JOBS
    assert unfinished == 0, "la file contient encore des jobs pending/running après drainage"
