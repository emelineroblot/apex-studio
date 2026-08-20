"""Schémas des indicateurs — taux de rattachement automatique (J2), dashboard (J3)."""

from pydantic import BaseModel


class AutoAttachRate(BaseModel):
    total: int
    auto_time: int
    auto_ocr: int
    human: int
    unattached: int
    rate: float


class MediaIngestedVolume(BaseModel):
    real: int
    simulated: int
    total: int


class DashboardOut(BaseModel):
    """4 indicateurs, lus tels quels depuis une seule requête SQL — jamais recalculés en UI."""

    revenue_cents: int
    shootings_done: int
    shootings_upcoming: int
    media_ingested: MediaIngestedVolume
    auto_attach_rate: float
