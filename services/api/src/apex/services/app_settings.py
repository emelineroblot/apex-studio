"""Lecture des réglages `app_setting` (§3-G.3 du plan) avec repli sur des valeurs par
défaut codées — les seuils eux-mêmes ne sont **jamais** codés en dur dans le pipeline,
seule leur valeur de repli l'est, au cas où la ligne n'existe pas encore en base (avant
tout `PUT` de configuration).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from apex.models.setting import AppSetting

# Regroupement des rafales (§3-G.3) : deux paramètres.
BURST_GAP_SECONDS_KEY = "burst_gap_seconds"
BURST_GAP_SECONDS_DEFAULT = 2.0
PHASH_MAX_DISTANCE_KEY = "phash_max_distance"
PHASH_MAX_DISTANCE_DEFAULT = 10


def get_setting(session: Session, key: str, default: Any) -> Any:
    row = session.execute(select(AppSetting).where(AppSetting.key == key)).scalar_one_or_none()
    if row is None:
        return default
    value = row.value
    # Stocké en JSONB — un scalaire est parfois enveloppé `{"value": ...}` par convenance
    # d'édition UI, parfois écrit nu. On accepte les deux pour rester tolérant en lecture.
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def get_burst_gap_seconds(session: Session) -> float:
    return float(get_setting(session, BURST_GAP_SECONDS_KEY, BURST_GAP_SECONDS_DEFAULT))


def get_phash_max_distance(session: Session) -> int:
    return int(get_setting(session, PHASH_MAX_DISTANCE_KEY, PHASH_MAX_DISTANCE_DEFAULT))
