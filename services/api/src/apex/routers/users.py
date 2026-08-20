"""`GET /users` (revue J1) — manque de contrat signalé par le frontend : l'écran
« Équipe » (affectation de photographes à un shooting, `PUT /shootings/{id}/staff`) est
inutilisable en live sans un moyen de lister les comptes internes.

Cloisonné `owner` uniquement (§3-I, matrice, colonne « Seuils OCR, réinitialisation
démo » et l'esprit général de la matrice pour toute opération d'administration des
comptes) : c'est le dirigeant qui affecte l'équipe, et lister l'ensemble des comptes
internes (même restreint à id/nom/rôle) est une opération d'administration, pas une
lecture de référentiel ouverte au photographe.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from apex.db import get_db
from apex.models.user import AppUser
from apex.schemas.user import UserSummary
from apex.security import require_role

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "",
    response_model=list[UserSummary],
    summary="Liste des comptes internes (id, nom, rôle) — pour l'affectation d'équipe",
    dependencies=[require_role("owner")],
)
def list_users(db: Session = Depends(get_db)) -> list[UserSummary]:
    stmt = select(AppUser).where(AppUser.is_active).order_by(AppUser.full_name)
    users = db.execute(stmt).scalars().all()
    return [UserSummary.model_validate(u) for u in users]
