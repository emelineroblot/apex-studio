"""`GET /dashboard` (J3) — 4 indicateurs lus en une seule requête SQL, jamais recalculés en UI."""

from fastapi import APIRouter, Security

from apex.routers._common import bearer_scheme, not_implemented
from apex.schemas.stats import DashboardOut

router = APIRouter(tags=["dashboard"], dependencies=[Security(bearer_scheme)])


@router.get("/dashboard", response_model=DashboardOut, summary="Tableau de bord dirigeant")
def dashboard(from_: str | None = None, to: str | None = None) -> DashboardOut:
    not_implemented("GET /dashboard")
