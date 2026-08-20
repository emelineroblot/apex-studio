"""Comptes de démo pré-remplis (§3-I du plan : « comptes de démo créés par le seed »).

**Écart de périmètre documenté** : le générateur de jeu de démo complet (~15 shootings,
~8000 médias) est explicitement hors périmètre J1 (brief, « hors périmètre — à ne pas
rouvrir »). Mais le critère d'acceptation J1 « comptes de test pré-remplis » et
`GET /demo/accounts` exigent que **2 comptes internes** existent réellement en base pour
que le login démo fonctionne. `ensure_demo_users()` est ce bootstrap minimal — idempotent,
appelé au démarrage de l'application (`main.py`) — sans rien du générateur J2/J3 (pas de
clients, shootings, médias simulés).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from apex.config import settings
from apex.models.user import AppUser
from apex.schemas.auth import Role
from apex.security import hash_password


@dataclass(frozen=True, slots=True)
class DemoAccountSpec:
    role: Role
    email: str
    password: str
    full_name: str
    label: str


def _specs() -> list[DemoAccountSpec]:
    return [
        DemoAccountSpec(
            role="owner",
            email="dirigeant@studio-chicane.dev",
            password=settings.demo_owner_password,
            full_name="Camille Vasseur",
            label="Se connecter en dirigeant",
        ),
        DemoAccountSpec(
            role="photographer",
            email="photographe@studio-chicane.dev",
            password=settings.demo_photographer_password,
            full_name="Lou Bertin",
            label="Se connecter en photographe",
        ),
    ]


def demo_account_specs() -> list[DemoAccountSpec]:
    return _specs()


def ensure_demo_users(session: Session) -> None:
    """Crée les 2 comptes de démo s'ils n'existent pas déjà. Idempotent, ne committe pas."""
    for spec in _specs():
        existing = session.execute(
            select(AppUser).where(AppUser.email == spec.email)
        ).scalar_one_or_none()
        if existing is not None:
            continue
        session.add(
            AppUser(
                email=spec.email,
                password_hash=hash_password(spec.password),
                full_name=spec.full_name,
                role=spec.role,
                is_active=True,
            )
        )
