"""File de tâches : `GET /queue/stats` (interne), `POST /jobs/tick` (serverless, secret
partagé `WORKER_SECRET` — pas de JWT, §3-E.7).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apex.config import settings
from apex.db import SessionLocal, get_db
from apex.models.job import Job
from apex.queue.runner import drain
from apex.schemas.job import QueueStats, TickResponse
from apex.security import CurrentUser

router = APIRouter(tags=["jobs"])

# §3-E.7 : budget aligné sur le `maxDuration=300s` Vercel, moins une marge — `drain()`
# revient bien avant si la file s'épuise, ce budget n'est qu'un plafond de sécurité.
JOBS_TICK_BUDGET_SECONDS = 250.0


@router.get(
    "/queue/stats",
    response_model=QueueStats,
    summary="État de la file",
)
def queue_stats(user: CurrentUser, db: Session = Depends(get_db)) -> QueueStats:
    counts: dict[str, int] = dict(
        db.execute(select(Job.status, func.count()).group_by(Job.status)).all()  # type: ignore[arg-type]
    )
    oldest_pending = db.execute(
        select(func.min(Job.run_at)).where(Job.status == "pending")
    ).scalar_one()
    oldest_pending_age_s = (
        (datetime.now(UTC) - oldest_pending).total_seconds() if oldest_pending else None
    )
    return QueueStats(
        pending=counts.get("pending", 0),
        running=counts.get("running", 0),
        dead=counts.get("dead", 0),
        oldest_pending_age_s=oldest_pending_age_s,
    )


@router.post(
    "/jobs/tick",
    response_model=TickResponse,
    summary="Drainer la file jusqu'à épuisement ou budget de temps (worker tiré, §3-E.7)",
)
def jobs_tick(x_worker_secret: str = Header(..., alias="X-Worker-Secret")) -> TickResponse:
    # 🟡 : comparaison à temps constant — un `!=` sur des secrets fuit leur longueur/préfixe
    # par timing (mineur ici, secret partagé côté serveur uniquement, mais sans coût à corriger).
    if not secrets.compare_digest(x_worker_secret, settings.worker_secret):
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_worker_secret", "message": "Secret invalide.", "detail": None},
        )
    deadline = datetime.now(UTC) + timedelta(seconds=JOBS_TICK_BUDGET_SECONDS)
    # `worker_id` unique par requête (§3-E.4, garantie 3) — voir `queue/runner.py`.
    result = drain(SessionLocal, f"http-tick-{uuid4().hex[:12]}", deadline=deadline)
    return TickResponse(**result.as_tick_response())
