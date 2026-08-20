"""`POST /auth/login`, `GET /auth/me` — JWT interne (§3-I du plan)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from apex.db import get_db
from apex.models.user import AppUser
from apex.schemas.auth import LoginRequest, TokenResponse, UserOut
from apex.security import CurrentUser, create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse, summary="Connexion par e-mail/mot de passe")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
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
