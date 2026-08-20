"""Routes top-level qui ne s'accrochent à aucun préfixe de ressource parente (J3) :
`DELETE /share-links/{id}`, `GET /deliveries/{id}`.
"""

import uuid

from fastapi import APIRouter, Security

from apex.routers._common import bearer_scheme, not_implemented
from apex.schemas.billing import DeliveryOut

router = APIRouter(tags=["sharing"], dependencies=[Security(bearer_scheme)])


@router.delete("/share-links/{share_link_id}", status_code=204, summary="Révoquer un lien")
def revoke_share_link(share_link_id: uuid.UUID) -> None:
    not_implemented("DELETE /share-links/{id}")


@router.get("/deliveries/{delivery_id}", response_model=DeliveryOut, summary="Suivi de livraison")
def get_delivery(delivery_id: int) -> DeliveryOut:
    not_implemented("GET /deliveries/{id}")
