"""`GET /stats/auto-attach-rate` (J2)."""

from fastapi import APIRouter, Security

from apex.routers._common import bearer_scheme, not_implemented
from apex.schemas.stats import AutoAttachRate

router = APIRouter(prefix="/stats", tags=["stats"], dependencies=[Security(bearer_scheme)])


@router.get(
    "/auto-attach-rate", response_model=AutoAttachRate, summary="Taux de rattachement automatique"
)
def auto_attach_rate(
    shooting_id: int | None = None, from_: str | None = None, to: str | None = None
) -> AutoAttachRate:
    not_implemented("GET /stats/auto-attach-rate")
