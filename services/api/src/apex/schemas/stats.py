"""Schémas des indicateurs — taux de rattachement automatique (J2), dashboard (J3)."""

from pydantic import BaseModel


class AutoAttachRatePopulation(BaseModel):
    """Même décompte que `AutoAttachRate`, restreint à une seule population (réel ou simulé)."""

    total: int
    auto_time: int
    auto_ocr: int
    human: int
    unattached: int
    rate: float


class AutoAttachRate(BaseModel):
    """Champs de tête : agrégat **toutes origines confondues** (rétrocompatible avec la
    forme d'origine du contrat). `real`/`simulated` (revue J2, 🟠 n°1, §3-N.1 du plan)
    ventilent le même calcul par `media.is_simulated` — un tableau de bord ne doit jamais
    annoncer un taux sans pouvoir dire sur quelle population il porte.
    """

    total: int
    auto_time: int
    auto_ocr: int
    human: int
    unattached: int
    rate: float
    real: AutoAttachRatePopulation
    simulated: AutoAttachRatePopulation


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
