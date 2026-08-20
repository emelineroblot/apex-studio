"""Combine les deux garanties du critère d'acceptation « le worker traite la file sans
double-traitement, même avec plusieurs workers concurrents » **et** « y compris quand un
drain s'arrête sur son budget de temps » — testées séparément par
`tests/queue/test_concurrency.py` (8 threads, `deadline=None`) et
`tests/queue/test_drain_deadline.py` (1 thread, `deadline` serré). Aucun des deux ne
prouve l'intersection : plusieurs workers concurrents dont certains expirent leur budget
en cours de lot, pendant que d'autres continuent de réclamer — c'est le scénario réel d'un
déploiement avec plusieurs requêtes `POST /jobs/tick` simultanées (§3-E.7).
"""

from __future__ import annotations

import datetime
import threading
import time

from sqlalchemy import func, select

from apex.db import SessionLocal
from apex.models.job import Job, JobExecutionLog
from apex.queue.enqueue import enqueue
from apex.queue.registry import JobContext, handler
from apex.queue.runner import drain

TOTAL_JOBS = 150
WORKER_THREADS = 6
JOB_DURATION_SECONDS = 0.05
PROBE_KIND = "test_concurrency_deadline_probe"


@handler(PROBE_KIND, max_attempts=3)
def _probe_handler(ctx: JobContext) -> dict[str, bool]:
    time.sleep(JOB_DURATION_SECONDS)
    # Même preuve que `test_concurrency.py` : une violation d'unicité ici prouverait un
    # double traitement.
    ctx.session.add(JobExecutionLog(job_id=ctx.job.id, worker_id=ctx.worker_id))
    ctx.session.flush()
    return {"ok": True}


def test_no_double_processing_when_some_workers_hit_their_deadline_mid_batch() -> None:
    seed_session = SessionLocal()
    try:
        for i in range(TOTAL_JOBS):
            enqueue(seed_session, PROBE_KIND, {"i": i}, dedupe_key=f"deadline-probe:{i}")
        seed_session.commit()
    finally:
        seed_session.close()

    errors: list[BaseException] = []

    def _run_worker(worker_id: str, *, with_deadline: bool) -> None:
        try:
            deadline = None
            if with_deadline:
                # Volontairement serré : chaque worker à deadline expirera en plein
                # traitement d'un lot de 10, laissant nécessairement des jobs réclamés non
                # exécutés à relâcher (`release_unclaimed`, §3-E, bloquant n°2).
                deadline = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
                    seconds=JOB_DURATION_SECONDS * 2.5
                )
            # `deadline=None` : ce worker draine jusqu'à épuisement de la file, en
            # concurrence directe avec les workers à deadline courte — c'est l'intersection
            # des deux scénarios que ce test vérifie.
            while True:
                result = drain(SessionLocal, worker_id, deadline=deadline, batch_size=10)
                if deadline is not None:
                    break
                if result.claimed == 0:
                    break
        except BaseException as exc:  # noqa: BLE001 — remonté dans le thread principal
            errors.append(exc)

    threads = [
        threading.Thread(
            target=_run_worker, args=(f"deadline-worker-{i}",), kwargs={"with_deadline": True}
        )
        for i in range(WORKER_THREADS - 1)
    ]
    threads.append(
        threading.Thread(
            target=_run_worker, args=("sweep-worker",), kwargs={"with_deadline": False}
        )
    )
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert not errors, f"un ou plusieurs workers ont levé une exception : {errors}"

    # Les workers à deadline courte laissent nécessairement du travail derrière eux — le
    # worker « sweep » (deadline=None) doit finir le lot, éventuellement en plusieurs
    # passes, tant qu'il reste des jobs `pending`.
    finisher = SessionLocal()
    try:
        for _ in range(20):
            remaining = finisher.execute(
                select(func.count())
                .select_from(Job)
                .where(Job.kind == PROBE_KIND, Job.status.in_(("pending", "running")))
            ).scalar_one()
            if remaining == 0:
                break
            drain(SessionLocal, "sweep-worker-final", deadline=None, batch_size=10)
    finally:
        finisher.close()

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
        running_stuck = check_session.execute(
            select(func.count())
            .select_from(Job)
            .where(Job.kind == PROBE_KIND, Job.status == "running")
        ).scalar_one()
    finally:
        check_session.close()

    # Le cœur du critère : ni doublon (violation d'unicité aurait fini dans `errors`
    # ci-dessus), ni job perdu, ni job abandonné en `running` par un worker qui a expiré.
    assert log_count == TOTAL_JOBS, f"attendu {TOTAL_JOBS} logs, obtenu {log_count}"
    assert distinct_job_ids == TOTAL_JOBS, "un même job_id a été traité plusieurs fois"
    assert done_count == TOTAL_JOBS
    assert unfinished == 0
    assert running_stuck == 0, "un job est resté 'running' — une réclamation n'a pas été relâchée"
