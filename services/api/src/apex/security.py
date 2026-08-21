"""Authentification (§3-I du plan) — bcrypt, JWT HS256, dépendances FastAPI de rôle.

**Écart documenté au plan** : le plan prescrit `passlib[bcrypt]`. En pratique, la
combinaison installée `passlib==1.7.4` + `bcrypt==5.0.0` est cassée — `passlib` sonde
`bcrypt.__about__.__version__`, retiré depuis `bcrypt>=4.1`, et lève `AttributeError`
avant même de hacher (reproduit : `ValueError: password cannot be longer than 72 bytes`
dès le premier `.hash()`, bien en-deçà de la limite). Plutôt que d'épingler une version
de `bcrypt` obsolète pour satisfaire un wrapper devenu inutile, ce module appelle
directement la bibliothèque `bcrypt` (déjà une dépendance transitive de
`passlib[bcrypt]`) — l'algorithme reste bcrypt, seule la couche d'indirection change.
À signaler en revue.

Deux portées de jeton (§3-I, §3-L) : interne (`owner`/`photographer`, TTL 8 h) et session
client (J3, TTL 30 min) — seule la portée interne est câblée en J1.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import bcrypt
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from apex.config import settings
from apex.db import get_db
from apex.models.billing import ShareLink
from apex.models.user import AppUser
from apex.routers._common import bearer_scheme
from apex.services import sharing

JWT_ALGORITHM = "HS256"
INTERNAL_TOKEN_SCOPE = "internal"
CLIENT_TOKEN_SCOPE = "client"

BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    """Hache un mot de passe en bcrypt. Tronque à 72 octets (limite dure de bcrypt)."""
    raw = password.encode("utf-8")[:BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    raw = password.encode("utf-8")[:BCRYPT_MAX_BYTES]
    try:
        return bcrypt.checkpw(raw, password_hash.encode("ascii"))
    except ValueError:
        # Hash malformé/vide — jamais une exception qui casserait le flux de login.
        return False


def create_access_token(user: AppUser) -> tuple[str, int]:
    """Renvoie `(token, expires_in_seconds)` — TTL interne (§3-I, 8 h par défaut)."""
    ttl = timedelta(minutes=settings.jwt_ttl_minutes)
    expires_at = datetime.now(UTC) + ttl
    payload: dict[str, Any] = {
        "sub": str(user.id),
        "role": user.role,
        "scope": INTERNAL_TOKEN_SCOPE,
        "exp": expires_at,
        "iat": datetime.now(UTC),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)
    return token, int(ttl.total_seconds())


def _decode_token(token: str) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "invalid_token",
                "message": "Jeton invalide ou expiré.",
                "detail": None,
            },
        ) from exc
    return payload


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> AppUser:
    """Dépendance FastAPI — résout et vérifie le JWT interne, charge l'utilisateur actif."""
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "not_authenticated",
                "message": "Authentification requise.",
                "detail": None,
            },
        )
    payload = _decode_token(credentials.credentials)
    if payload.get("scope") != INTERNAL_TOKEN_SCOPE:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "invalid_token",
                "message": "Portée de jeton invalide.",
                "detail": None,
            },
        )
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_token", "message": "Jeton invalide.", "detail": None},
        ) from exc

    user = db.execute(select(AppUser).where(AppUser.id == user_id)).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "invalid_token",
                "message": "Utilisateur inconnu ou désactivé.",
                "detail": None,
            },
        )
    return user


CurrentUser = Annotated[AppUser, Depends(get_current_user)]


def require_role(*roles: str) -> Any:
    """Dépendance paramétrée — `403` si le rôle courant n'est pas dans `roles` (§3-I)."""

    def _dependency(user: CurrentUser) -> AppUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "forbidden",
                    "message": "Ce rôle n'a pas accès à cette ressource.",
                    "detail": None,
                },
            )
        return user

    return Depends(_dependency)


# --- Portée client : session courte de l'espace de partage (§3-L.2) --------------------


@dataclass(frozen=True, slots=True)
class ClientScope:
    """Périmètre d'une session client — **la seule source d'autorité** du routeur `/public`.

    Aucun endpoint public n'accepte d'identifiant de collection ou de client : ils viennent
    d'ici, donc du jeton, jamais de la requête (§3-L.3).
    """

    share_link_id: uuid.UUID
    collection_id: int
    client_id: int


def create_client_session_token(link: ShareLink, client_id: int) -> tuple[str, int]:
    """JWT de 30 min échangé contre le jeton long (§3-L.2).

    Le jeton long ne doit pas circuler à chaque requête : il apparaîtrait dans le `src` de
    chaque vignette, donc dans les journaux du navigateur, du proxy et de l'hébergeur.
    """
    ttl = timedelta(minutes=settings.client_session_ttl_minutes)
    payload: dict[str, Any] = {
        "sub": str(link.id),
        "scope": CLIENT_TOKEN_SCOPE,
        "collection_id": link.collection_id,
        "client_id": client_id,
        "exp": datetime.now(UTC) + ttl,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM), int(
        ttl.total_seconds()
    )


def get_client_scope(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> ClientScope:
    """Dépendance **unique** du routeur `/public`.

    Revalide le lien de partage en base à chaque requête, et pas seulement à l'ouverture de
    session : sans cela, un lien révoqué resterait exploitable jusqu'à l'expiration du JWT,
    soit une demi-heure — alors que « révocation immédiate » est un critère d'acceptation.
    """
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "not_authenticated",
                "message": "Session client requise.",
                "detail": None,
            },
        )
    payload = _decode_token(credentials.credentials)
    if payload.get("scope") != CLIENT_TOKEN_SCOPE:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "invalid_token",
                "message": "Portée de jeton invalide.",
                "detail": None,
            },
        )
    try:
        link_id = uuid.UUID(str(payload["sub"]))
        collection_id = int(payload["collection_id"])
        client_id = int(payload["client_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_token", "message": "Jeton invalide.", "detail": None},
        ) from exc

    link = db.execute(select(ShareLink).where(ShareLink.id == link_id)).scalar_one_or_none()
    if link is None or link.collection_id != collection_id:
        # Le lien a disparu (collection supprimée en cascade) ou le jeton a été forgé avec
        # une collection qui n'est pas la sienne — indiscernables, traités pareil.
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_token", "message": "Session invalide.", "detail": None},
        )
    try:
        sharing.assert_usable(link)
    except sharing.ShareLinkExpired as exc:
        raise HTTPException(
            status_code=410,
            detail={
                "code": "link_expired",
                "message": "Ce lien de partage n'est plus valide.",
                "detail": None,
            },
        ) from exc

    return ClientScope(share_link_id=link.id, collection_id=collection_id, client_id=client_id)


CurrentClient = Annotated[ClientScope, Depends(get_client_scope)]
