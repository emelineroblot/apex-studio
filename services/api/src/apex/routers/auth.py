"""`POST /auth/login`, `GET /auth/me` — JWT interne (§3-I du plan)."""

import time
from collections import defaultdict
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from apex.db import get_db
from apex.models.user import AppUser
from apex.schemas.auth import LoginRequest, TokenResponse, UserOut
from apex.security import CurrentUser, create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# 🟡 : limitation de débit sur `/auth/login` — absente jusqu'ici. Implémentation en
# mémoire de processus (pas de Redis/service tiers, §Garde-fous) : fenêtre glissante par
# clé `email|IP`. Limite documentée : se réinitialise à froid en serverless (chaque
# invocation peut démarrer un nouveau processus) — acceptable pour une démo à données
# fictives (§AGENTS.md, « risque accepté »), pas un rempart absolu contre le brute-force
# distribué. Un vrai déploiement multi-instance voudrait un compteur partagé (table
# Postgres, déjà la brique disponible ici) plutôt qu'un service de rate-limiting tiers.
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 10
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 60.0
_login_attempts: dict[str, list[float]] = defaultdict(list)
_login_attempts_lock = Lock()


def _enforce_login_rate_limit(key: str) -> None:
    now = time.monotonic()
    with _login_attempts_lock:
        attempts = _login_attempts[key]
        attempts[:] = [t for t in attempts if now - t < LOGIN_RATE_LIMIT_WINDOW_SECONDS]
        if len(attempts) >= LOGIN_RATE_LIMIT_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "rate_limited",
                    "message": "Trop de tentatives de connexion — réessayez dans une minute.",
                    "detail": None,
                },
            )
        attempts.append(now)


@router.post("/login", response_model=TokenResponse, summary="Connexion par e-mail/mot de passe")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    client_ip = request.client.host if request.client else "unknown"
    _enforce_login_rate_limit(f"{payload.email.lower()}|{client_ip}")

    user = db.execute(select(AppUser).where(AppUser.email == payload.email)).scalar_one_or_none()
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "invalid_credentials",
                "message": "E-mail ou mot de passe incorrect.",
                "detail": None,
            },
        )
    token, expires_in = create_access_token(user)
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut, summary="Utilisateur courant")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
