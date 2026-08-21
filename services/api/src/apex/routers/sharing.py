"""Routes top-level qui ne s'accrochent à aucun préfixe de ressource parente (J3) :
`DELETE /share-links/{id}`, `GET /deliveries/{id}`.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Security
from sqlalchemy.orm import Session

from apex.db import get_db
from apex.models.billing import Delivery, ShareLink
from apex.routers._common import bearer_scheme
from apex.schemas.billing import DeliveryOut
from apex.security import CurrentUser
from apex.services import access

router = APIRouter(tags=["sharing"], dependencies=[Security(bearer_scheme)])


@router.delete("/share-links/{share_link_id}", status_code=204, summary="Révoquer un lien")
def revoke_share_link(
    share_link_id: uuid.UUID, user: CurrentUser, db: Session = Depends(get_db)
) -> None:
    """Révocation immédiate, et vraiment immédiate : `security.get_client_scope` relit le
    lien à **chaque** requête de l'espace client, donc une session déjà ouverte s'éteint
    au prochain appel plutôt qu'à l'expiration de son JWT une demi-heure plus tard."""
    access.require_owner(user, message="Seul le dirigeant peut révoquer un lien de partage.")
    link = db.get(ShareLink, share_link_id)
    if link is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "Lien introuvable.", "detail": None},
        )
    # Idempotent : révoquer deux fois n'est pas une erreur, et surtout ne repousse pas la
    # date de révocation déjà enregistrée.
    if link.revoked_at is None:
        link.revoked_at = datetime.now(UTC)
        db.commit()


@router.get("/deliveries/{delivery_id}", response_model=DeliveryOut, summary="Suivi de livraison")
def get_delivery(delivery_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> DeliveryOut:
    """Vue studio de la preparation. Le champ `error` est ce qui rend une livraison
    echouee actionnable : sans lui, il ne resterait qu'un statut rouge sans cause."""
    delivery = db.get(Delivery, delivery_id)
    if delivery is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "Livraison introuvable.", "detail": None},
        )
    return DeliveryOut.model_validate(delivery)
