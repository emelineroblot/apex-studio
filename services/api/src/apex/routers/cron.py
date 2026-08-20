"""`POST /cron/nightly` — appelé par Vercel Cron (`Authorization: Bearer $CRON_SECRET`).

N'exécute jamais le reset lui-même : enqueue `demo_reset` puis déclenche un tick,
répond `202` (contrainte cron Hobby : 10 s max, §3-N.2 / R2).
"""

from fastapi import APIRouter, Header

from apex.routers._common import not_implemented
from apex.schemas.billing import CronResponse

router = APIRouter(tags=["cron"])


@router.post(
    "/cron/nightly",
    response_model=CronResponse,
    status_code=202,
    summary="Déclencheur nocturne — enqueue seulement, n'exécute rien",
)
def cron_nightly(authorization: str = Header(...)) -> CronResponse:
    not_implemented("POST /cron/nightly")
