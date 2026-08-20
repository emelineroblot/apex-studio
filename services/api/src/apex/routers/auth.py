"""`POST /auth/login`, `GET /auth/me` — squelette (Lot 0). Logique JWT/bcrypt au Lot 1."""

from fastapi import APIRouter, Security

from apex.routers._common import bearer_scheme, not_implemented
from apex.schemas.auth import LoginRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse, summary="Connexion par e-mail/mot de passe")
def login(payload: LoginRequest) -> TokenResponse:
    not_implemented("POST /auth/login")


@router.get(
    "/me",
    response_model=UserOut,
    summary="Utilisateur courant",
    dependencies=[Security(bearer_scheme)],
)
def me() -> UserOut:
    not_implemented("GET /auth/me")
