"""Schémas du référentiel : `client`, `circuit`, `driver`, `team`."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr

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


class CameraPatchResponse(BaseModel):
    """`reattach_job_id` est non nul si le décalage change : enqueue `reattach_camera`."""

    camera: CameraOut
    reattach_job_id: int | None = None
