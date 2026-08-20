"""Schémas `shooting`, `shooting_staff`, `engagement`."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

ShootingStatus = Literal["planned", "done"]


class ShootingCreate(BaseModel):
    client_id: int | None = None
    circuit_id: int
    title: str
    starts_at: datetime
    ends_at: datetime
    quota_bytes: int | None = None
    notes: str | None = None


class ShootingPatch(BaseModel):
    client_id: int | None = None
    circuit_id: int | None = None
    title: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    status: ShootingStatus | None = None
    quota_bytes: int | None = None
    notes: str | None = None


class ShootingSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int | None
    circuit_id: int
    title: str
    starts_at: datetime
    ends_at: datetime
    status: ShootingStatus
    media_count: int
    attached_count: int


class StaffMember(BaseModel):
    user_id: int
    role: str


class ShootingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int | None
    circuit_id: int
    title: str
    starts_at: datetime
    ends_at: datetime
    status: ShootingStatus
    quota_bytes: int
    notes: str | None
    staff: list[StaffMember]
    engagement_count: int


class StaffUpdateRequest(BaseModel):
    user_ids: list[int]


class StaffUpdateResponse(BaseModel):
    staff: list[StaffMember]


class EngagementCreate(BaseModel):
    car_number: str
    driver_id: int | None = None
    team_id: int | None = None
    client_id: int | None = None
    car_model: str | None = None


class EngagementPatch(BaseModel):
    car_number: str | None = None
    driver_id: int | None = None
    team_id: int | None = None
    client_id: int | None = None
    car_model: str | None = None


class EngagementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shooting_id: int
    car_number: str
    driver_id: int | None
    team_id: int | None
    client_id: int | None
    car_model: str | None


class EngagementImportError(BaseModel):
    line: int
    message: str


class EngagementImportResult(BaseModel):
    created: int
    skipped: int
    errors: list[EngagementImportError]
