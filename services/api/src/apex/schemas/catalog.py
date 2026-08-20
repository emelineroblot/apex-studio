"""Schémas du référentiel : `client`, `circuit`, `driver`, `team`."""

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

ClientKind = Literal["team", "driver", "sponsor"]


class ClientBase(BaseModel):
    name: str
    kind: ClientKind
    contact_name: str | None = None
    contact_email: EmailStr | None = None
    phone: str | None = None
    address: str | None = None
    notes: str | None = None


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: str | None = None
    kind: ClientKind | None = None
    contact_name: str | None = None
    contact_email: EmailStr | None = None
    phone: str | None = None
    address: str | None = None
    notes: str | None = None


class ClientOut(ClientBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class CircuitBase(BaseModel):
    name: str
    city: str | None = None
    country: str | None = None
    timezone: str = "Europe/Paris"


class CircuitCreate(CircuitBase):
    pass


class CircuitOut(CircuitBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class DriverBase(BaseModel):
    full_name: str
    nationality: str | None = None


class DriverCreate(DriverBase):
    pass


class DriverOut(DriverBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class TeamBase(BaseModel):
    name: str
    client_id: int | None = None


class TeamCreate(TeamBase):
    pass


class TeamOut(TeamBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class CameraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    exif_serial: str | None
    make: str | None
    model: str | None
    owner_user_id: int | None
    clock_offset_seconds: int
    timezone: str


class CameraPatch(BaseModel):
    clock_offset_seconds: int | None = None
    timezone: str | None = None
    owner_user_id: int | None = None

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str | None) -> str | None:
        """Revue J1 (🟠, scénario du bloquant n°1) : `timezone=""` (ou tout nom invalide)
        n'était pas validé — `ZoneInfo("")` lève `ValueError` plus tard dans le pipeline
        d'ingestion, hors du chemin de test habituel. Rejeté ici, au plus tôt, en `422`.
        """
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Fuseau horaire inconnu : « {value} ».") from exc
        return value


class CameraPatchResponse(BaseModel):
    """`reattach_job_id` est non nul si le décalage/fuseau change : enqueue
    `reattach_camera`. `reattached` (revue J1, 🟠) reflète le compte déjà calculé par le
    handler (`reattach_camera.py`) — `None` si le tick déclenché après l'enqueue n'a pas eu
    le temps de terminer ce job avant la réponse (file chargée) : l'appelant doit alors
    suivre `reattach_job_id` via `GET /queue/stats` plutôt que supposer `0`.
    """

    camera: CameraOut
    reattach_job_id: int | None = None
    reattached: int | None = None
