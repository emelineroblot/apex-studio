"""`GET /users` — manque de contrat signalé par le frontend (revue J1) : sans lui,
l'affectation d'équipe (`PUT /shootings/{id}/staff`) est inutilisable en live. Réponse
volontairement restreinte au strict nécessaire (id, nom, rôle) — pas d'e-mail, pas de
statut, pour ne pas exposer plus que ce que l'écran d'affectation a besoin d'afficher.
"""

from pydantic import BaseModel, ConfigDict

from apex.schemas.auth import Role


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    role: Role
