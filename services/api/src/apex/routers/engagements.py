"""`PATCH/DELETE /engagements/{id}` — la création vit sous `/shootings/{id}/engagements`."""

from fastapi import APIRouter, Security

from apex.routers._common import bearer_scheme, not_implemented
from apex.schemas.shooting import EngagementOut, EngagementPatch

router = APIRouter(
    prefix="/engagements", tags=["engagements"], dependencies=[Security(bearer_scheme)]
)


@router.patch("/{engagement_id}", response_model=EngagementOut, summary="Modifier un engagement")
def patch_engagement(engagement_id: int, payload: EngagementPatch) -> EngagementOut:
    not_implemented("PATCH /engagements/{id}")


@router.delete("/{engagement_id}", status_code=204, summary="Supprimer un engagement")
def delete_engagement(engagement_id: int) -> None:
    not_implemented("DELETE /engagements/{id}")
