"""Comptes et jeu de démonstration — `GET /demo/accounts` (public, J1), `POST /demo/seed`
(J2, secret serveur), `POST /demo/reset` (J3, cron).
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Security
from sqlalchemy.orm import Session

from apex.config import settings
from apex.db import get_db
from apex.demo.accounts import demo_account_specs
from apex.queue.enqueue import enqueue, enqueue_unique_pending
from apex.routers._common import bearer_scheme, not_implemented
from apex.schemas.auth import DemoAccount
from apex.schemas.billing import DemoResetResponse

router = APIRouter(prefix="/demo", tags=["demo"])


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
    status_code=202,
    summary="Régénère le jeu de démo (J2) — secret serveur (`WORKER_SECRET`), pas un rôle",
)
def demo_seed(
    x_worker_secret: str = Header(..., alias="X-Worker-Secret"),
    db: Session = Depends(get_db),
    reset: bool = False,
) -> DemoResetResponse:
    """Enqueue `demo_reset` (§3-N.2) puis répond immédiatement — la file reste l'unique
    chemin d'écriture, un tick (`POST /jobs/tick`, `apex.cli worker --loop`) le draine.

    **Revue J2 (🔴 n°3)** : cette route TRUNCATE 25 tables. `require_owner` (JWT) ne protège
    rien ici puisque `GET /demo/accounts` est **public** et publie le mot de passe `owner`
    en clair (design assumé — self-service de connexion pour la démo, §3-I) : trois appels
    HTTP suffisaient à effacer la base en pleine démonstration. Découplé de l'identité du
    déclencheur — même patron que `POST /jobs/tick` (`routers/jobs.py`) : un secret serveur
    (`WORKER_SECRET`), jamais exposé au navigateur, jamais un JWT.

    Le drainage synchrone dans la requête a également été retiré (même revue) : il exécutait
    n'importe quel job déjà en file — y compris des inférences OCR — dans le budget de la
    requête HTTP (60 s, alors que le pool ne compte que 2+3 connexions), rendant l'API
    indisponible sous quelques appels concurrents. `DemoResetResponse` porte déjà `job_id` :
    la redistribution est visible au prochain tick, jamais bloquante pour l'appelant.
    """
    # 🟡 : comparaison à temps constant — cf. `routers/jobs.py::jobs_tick`, même motif.
    if not secrets.compare_digest(x_worker_secret, settings.worker_secret):
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_worker_secret", "message": "Secret invalide.", "detail": None},
        )

    job_id = enqueue(db, "demo_reset", {"reset": reset}, dedupe_key="demo_reset", priority=10)
    if job_id is None:
        job_id = enqueue_unique_pending(db, "demo_reset", "demo_reset")
    if job_id is None:
        job_id = enqueue(db, "demo_reset", {"reset": reset}, priority=10)
    assert job_id is not None
    db.commit()

    return DemoResetResponse(job_id=job_id)


@router.post(
    "/reset",
    response_model=DemoResetResponse,
    summary="Réinitialisation nocturne — `owner` uniquement (J3)",
    dependencies=[Security(bearer_scheme)],
)
def demo_reset() -> DemoResetResponse:
    not_implemented("POST /demo/reset")
