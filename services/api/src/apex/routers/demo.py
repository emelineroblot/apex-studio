"""Comptes et jeu de démonstration — `GET /demo/accounts` (public, J1), `POST /demo/seed`
(J2), `POST /demo/reset` (J3, `owner` uniquement).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, Security
from sqlalchemy.orm import Session

from apex.db import SessionLocal, get_db
from apex.demo.accounts import demo_account_specs
from apex.queue.enqueue import enqueue, enqueue_unique_pending
from apex.queue.runner import drain
from apex.routers._common import bearer_scheme, not_implemented
from apex.schemas.auth import DemoAccount
from apex.schemas.billing import DemoResetResponse
from apex.security import CurrentUser
from apex.services import access

router = APIRouter(prefix="/demo", tags=["demo"])

#: Budget de drainage après l'enqueue — le seed vise < 15 s (§3-N.1) ; large marge pour
#: absorber une base de test/démo plus lente sans faire échouer la requête HTTP.
SEED_DRAIN_BUDGET = timedelta(seconds=60)


@router.get(
    "/accounts",
    response_model=list[DemoAccount],
    summary="Comptes de démo pré-remplis (public)",
)
def demo_accounts() -> list[DemoAccount]:
    return [
        DemoAccount(role=spec.role, email=spec.email, password=spec.password, label=spec.label)
        for spec in demo_account_specs()
    ]


@router.post(
    "/seed",
    response_model=DemoResetResponse,
    summary="Régénère le jeu de démo (J2) — `owner` uniquement",
    dependencies=[Security(bearer_scheme)],
)
def demo_seed(
    user: CurrentUser, db: Session = Depends(get_db), reset: bool = False
) -> DemoResetResponse:
    """Enqueue `demo_reset` (§3-N.2) puis draine — même patron que `PUT /settings/ocr`
    (§3-E.7) : la file reste l'unique chemin d'écriture, mais la démo veut un résultat
    perceptible dès la réponse HTTP plutôt qu'une attente du prochain tick.
    """
    access.require_owner(user, message="Seul le dirigeant peut régénérer le jeu de démo.")

    job_id = enqueue(db, "demo_reset", {"reset": reset}, dedupe_key="demo_reset", priority=10)
    if job_id is None:
        job_id = enqueue_unique_pending(db, "demo_reset", "demo_reset")
    if job_id is None:
        job_id = enqueue(db, "demo_reset", {"reset": reset}, priority=10)
    assert job_id is not None
    db.commit()

    db.rollback()  # relâche la connexion avant que `drain()` en réclame une (cf. settings.py)
    drain(
        SessionLocal,
        f"http-demo-seed-{uuid4().hex[:12]}",
        deadline=datetime.now(UTC) + SEED_DRAIN_BUDGET,
        batch_size=1,
    )

    return DemoResetResponse(job_id=job_id)


@router.post(
    "/reset",
    response_model=DemoResetResponse,
    summary="Réinitialisation nocturne — `owner` uniquement (J3)",
    dependencies=[Security(bearer_scheme)],
)
def demo_reset() -> DemoResetResponse:
    not_implemented("POST /demo/reset")
