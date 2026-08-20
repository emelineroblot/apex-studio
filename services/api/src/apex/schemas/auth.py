"""Schémas d'authentification et de démonstration (`POST /auth/login`, `GET /demo/accounts`)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr

Role = Literal["owner", "photographer"]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: Role


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class DemoAccount(BaseModel):
    """Pré-remplissage des 2 boutons de connexion démo côté frontend."""

    role: Role
    email: EmailStr
    password: str
    label: str
