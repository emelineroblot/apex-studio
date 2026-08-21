"""`POST /cron/nightly` — appelé par Vercel Cron (`Authorization: Bearer $CRON_SECRET`).

N'exécute jamais le reset lui-même : enqueue `demo_reset` puis déclenche un tick,
répond `202` (contrainte cron Hobby : 10 s max, §3-N.2 / R2).
"""

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from apex.config import settings
from apex.db import get_db
from apex.queue.enqueue import enqueue, enqueue_unique_pending
from apex.schemas.billing import CronResponse

router = APIRouter(tags=["cron"])


@router.post(
    "/cron/nightly",
    response_model=CronResponse,
    status_code=202,
    summary="Déclencheur nocturne — enqueue seulement, n'exécute rien",
)
def cron_nightly(authorization: str = Header(...), db: Session = Depends(get_db)) -> CronResponse:
    """N'execute **rien** : met un `demo_reset` en file et repond `202`.

    Contrainte de plateforme, pas choix de style : un cron Vercel Hobby dispose de 10
    secondes, la ou un reset complet en demande plusieurs dizaines. Inserer une ligne
    prend quelques millisecondes ; le vrai travail se fait dans le worker, avec ses 300
    secondes et son heartbeat (§3-N.2, Option 2).

    Le secret est compare a temps constant, comme `POST /jobs/tick` : un `!=` sur un
    secret partage fuit sa longueur et son prefixe par le temps de reponse.
    """
    expected = f"Bearer {settings.cron_secret}"
    if not secrets.compare_digest(authorization, expected):
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_cron_secret", "message": "Secret invalide.", "detail": None},
        )

    job_id = enqueue(db, "demo_reset", {"reset": True}, dedupe_key="demo_reset", priority=10)
    if job_id is None:
        job_id = enqueue_unique_pending(db, "demo_reset", "demo_reset")
    if job_id is None:
        job_id = enqueue(db, "demo_reset", {"reset": True}, priority=10)
    assert job_id is not None
    db.commit()
    return CronResponse(job_id=job_id)
