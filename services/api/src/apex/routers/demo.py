"""Comptes et jeu de démonstration — `GET /demo/accounts` (public, J1), `POST /demo/seed`
(J2), `POST /demo/reset` (J3, `owner` uniquement).
"""

from fastapi import APIRouter, Security

from apex.demo.accounts import demo_account_specs
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
    summary="Régénère le jeu de démo (J2)",
    dependencies=[Security(bearer_scheme)],
)
def demo_seed(reset: bool = False) -> DemoResetResponse:
    not_implemented("POST /demo/seed")


@router.post(
    "/reset",
    response_model=DemoResetResponse,
    summary="Réinitialisation nocturne — `owner` uniquement (J3)",
    dependencies=[Security(bearer_scheme)],
)
def demo_reset() -> DemoResetResponse:
    not_implemented("POST /demo/reset")
