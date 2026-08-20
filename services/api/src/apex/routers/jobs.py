"""File de tâches : `GET /queue/stats` (interne), `POST /jobs/tick` (serverless, secret
partagé `WORKER_SECRET` — pas de JWT, §3-E.7).
"""

from fastapi import APIRouter, Header, Security

from apex.routers._common import bearer_scheme, not_implemented
from apex.schemas.job import QueueStats, TickResponse

router = APIRouter(tags=["jobs"])


@router.get(
    "/queue/stats",
    response_model=QueueStats,
    summary="État de la file",
    dependencies=[Security(bearer_scheme)],
)
def queue_stats() -> QueueStats:
    not_implemented("GET /queue/stats")


@router.post(
    "/jobs/tick",
    response_model=TickResponse,
    summary="Drainer la file jusqu'à épuisement ou budget de temps (worker tiré, §3-E.7)",
)
def jobs_tick(x_worker_secret: str = Header(..., alias="X-Worker-Secret")) -> TickResponse:
    not_implemented("POST /jobs/tick")
