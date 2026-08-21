"""Liens de partage de l'espace client (§3-L.1 du plan).

**Le jeton n'existe en clair qu'une fois**, à la création : la base ne stocke que son
`sha256`. Une fuite de la base ne donne accès à aucune collection — et personne, pas même
le studio, ne peut réafficher un lien perdu. C'est le compromis assumé d'un jeton traité
comme un secret : on en recrée un, on ne le récupère pas.

Jeton opaque plutôt que JWT dans l'URL (§3-L.1, Option 2) : un JWT serait non révocable,
or la révocation est un critère du brief — et une URL finit dans les historiques, les logs
de proxy et les captures d'écran.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from apex.config import settings
from apex.models.billing import ShareLink

#: 32 octets → 43 caractères URL-safe, 256 bits d'entropie. Non devinable par force brute.
TOKEN_BYTES = 32

#: Longueur du jeton en clair, utilisée pour composer une URL masquée qui a la même
#: silhouette que la vraie — le jeton, lui, est irrécupérable par conception.
_TOKEN_CHARS = 43


class ShareLinkError(Exception):
    """Base des refus de résolution — traduits en HTTP par le routeur, jamais ici."""


class ShareLinkNotFound(ShareLinkError):
    """Jeton inconnu → `404`, jamais `403` : ne pas révéler ce qui existe (§3-L.3)."""


class ShareLinkExpired(ShareLinkError):
    """Expiré ou révoqué → `410 Gone` + `{"code": "link_expired"}`, page métier dédiée."""


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


def build_share_url(token: str) -> str:
    return f"{settings.public_web_base_url.rstrip('/')}/c/{token}"


def masked_share_url() -> str:
    """URL d'affichage pour un lien déjà créé. Le jeton n'est pas récupérable : ce n'est
    pas une troncature du vrai lien mais une silhouette de même longueur. Les liens se
    distinguent entre eux par leur `id`, pas par cette chaîne."""
    return f"{settings.public_web_base_url.rstrip('/')}/c/{'•' * _TOKEN_CHARS}"


def create_share_link(
    session: Session, *, collection_id: int, created_by: int, expires_in_days: int
) -> tuple[ShareLink, str]:
    """Crée un lien et renvoie `(share_link, token_en_clair)`.

    L'appelant est le **seul** à voir le jeton, et une seule fois : il ne doit ni le
    journaliser, ni le persister ailleurs.
    """
    token = secrets.token_urlsafe(TOKEN_BYTES)
    link = ShareLink(
        collection_id=collection_id,
        token_hash=hash_token(token),
        expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
        created_by=created_by,
    )
    session.add(link)
    session.flush()
    return link, token


def resolve_token(session: Session, token: str) -> ShareLink:
    """Résout un jeton en clair. Lève `ShareLinkNotFound` ou `ShareLinkExpired`.

    Ne compte pas la vue : `POST /public/session` le fait explicitement, une fois par
    ouverture de session, pas à chaque requête d'image.
    """
    link = session.execute(
        select(ShareLink).where(ShareLink.token_hash == hash_token(token))
    ).scalar_one_or_none()
    if link is None:
        raise ShareLinkNotFound
    assert_usable(link)
    return link


def assert_usable(link: ShareLink) -> None:
    """Expiration et révocation, revérifiées **à chaque requête** de la session courte.

    Le JWT de session vit 30 minutes ; sans ce contrôle, un lien révoqué resterait ouvert
    jusqu'à une demi-heure après la révocation. « Révocation immédiate » est un critère
    d'acceptation, et un `SELECT` indexé par clé primaire est le prix négligeable à payer
    pour qu'il soit vrai.
    """
    if link.revoked_at is not None:
        raise ShareLinkExpired
    if link.expires_at <= datetime.now(UTC):
        raise ShareLinkExpired


def record_view(session: Session, link: ShareLink) -> None:
    """Trace une ouverture de session — `view_count`, `last_seen_at` (§3-L.1)."""
    link.view_count += 1
    link.last_seen_at = datetime.now(UTC)
    session.flush()
