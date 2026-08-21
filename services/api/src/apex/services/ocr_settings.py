"""**Directives** du principe DOE (§3-J.2 du plan) — les réglages de l'OCR vivent en base
(`app_setting`), jamais dans le code.

C'est la couche « quoi faire » : deux seuils de décision et trois paramètres de filtrage
géométrique. Aucun de ces nombres n'est un choix du modèle ; ce sont des *politiques*
éditables par le dirigeant depuis `/settings/ocr`, sans redéploiement.

Les constantes `*_DEFAULT` ci-dessous ne sont **pas** « les seuils codés en dur » : ce sont
les valeurs de repli utilisées tant que la ligne `app_setting` correspondante n'existe pas
(base fraîche, avant tout `PUT /settings/ocr`). Dès qu'une valeur est écrite en base, c'est
elle qui fait foi — y compris pour le worker.

Valeurs par défaut : issues de l'évaluation offline sur le jeu synthétique
(`tests/ocr/test_eval.py`, rapport `docs/ocr-eval.md`). Elles sont un **point de départ
calibré sur du synthétique**, pas une vérité sur photos réelles : rejouer l'éval sur le jeu
réel une fois sourcé et saisir les deux nombres dans l'UI suffit (aucune ligne de code).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from apex.models.setting import AppSetting

# --- Clés `app_setting` (§3-J.2) -------------------------------------------------------
OCR_HIGH_KEY = "ocr_high"
OCR_LOW_KEY = "ocr_low"
MIN_BOX_AREA_RATIO_KEY = "min_box_area_ratio"
MAX_BOX_AREA_RATIO_KEY = "max_box_area_ratio"
TOP_MARGIN_RATIO_KEY = "ocr_top_margin_ratio"
ENGINE_VERSION_KEY = "engine_version"

# --- Valeurs de repli (cf. docstring : ce ne sont pas « les seuils ») -------------------
#: Au-dessus → rattachement automatique.
#:
#: **0,85 et non 0,80** : le plan proposait 0,80 *avant* toute mesure. L'évaluation offline
#: (360 images, `docs/ocr-eval.md`) donne 97,7 % de précision à 0,80 — sous la cible de
#: 98 % — et 98,0 % à 0,85, pour 56,9 % de rattachement automatique au lieu de 59,4 %.
#: On paie 2,5 points d'automatisme pour supprimer un rattachement erroné sur cinq :
#: l'échange est le bon, une abstention coûte un clic quand un faux positif livre une photo
#: au mauvais client. C'est le balayage de seuils qui a tranché, pas une intuition.
OCR_HIGH_DEFAULT = 0.85
#: En dessous → abstention. Entre les deux → file de validation humaine.
OCR_LOW_DEFAULT = 0.45
#: Aire de la boîte détectée, en fraction de l'aire de l'image (§3-J.3, étape 3).
MIN_BOX_AREA_RATIO_DEFAULT = 0.0005
MAX_BOX_AREA_RATIO_DEFAULT = 0.08
#: Bande haute de l'image ignorée : le ciel ne porte pas de numéro de course.
TOP_MARGIN_RATIO_DEFAULT = 0.10
#: Version du moteur ayant produit les candidats — sert à l'idempotence de `ocr_media`.
ENGINE_VERSION_DEFAULT = "rapidocr-ppocrv4"


@dataclass(frozen=True, slots=True)
class OcrSettings:
    """Photo instantanée des Directives, lue une fois par job / par requête."""

    high: float
    low: float
    min_box_area_ratio: float
    max_box_area_ratio: float
    top_margin_ratio: float
    engine_version: str
    updated_at: datetime


def _unwrap(value: Any) -> Any:
    """`app_setting.value` est du JSONB : un scalaire est parfois nu, parfois enveloppé.

    Même tolérance de lecture que `services/app_settings.py` — on accepte les deux formes
    plutôt que d'imposer une convention à l'UI d'édition.
    """
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def load_ocr_settings(session: Session) -> OcrSettings:
    """Lit les Directives en une seule requête, avec repli sur les valeurs par défaut."""
    keys = (
        OCR_HIGH_KEY,
        OCR_LOW_KEY,
        MIN_BOX_AREA_RATIO_KEY,
        MAX_BOX_AREA_RATIO_KEY,
        TOP_MARGIN_RATIO_KEY,
        ENGINE_VERSION_KEY,
    )
    rows = list(session.execute(select(AppSetting).where(AppSetting.key.in_(keys))).scalars())
    raw = {row.key: _unwrap(row.value) for row in rows}
    updated_at = max((row.updated_at for row in rows), default=datetime.now(UTC))

    def _float(key: str, default: float) -> float:
        try:
            return float(raw[key])
        except (KeyError, TypeError, ValueError):
            return default

    return OcrSettings(
        high=_float(OCR_HIGH_KEY, OCR_HIGH_DEFAULT),
        low=_float(OCR_LOW_KEY, OCR_LOW_DEFAULT),
        min_box_area_ratio=_float(MIN_BOX_AREA_RATIO_KEY, MIN_BOX_AREA_RATIO_DEFAULT),
        max_box_area_ratio=_float(MAX_BOX_AREA_RATIO_KEY, MAX_BOX_AREA_RATIO_DEFAULT),
        top_margin_ratio=_float(TOP_MARGIN_RATIO_KEY, TOP_MARGIN_RATIO_DEFAULT),
        engine_version=str(raw.get(ENGINE_VERSION_KEY) or ENGINE_VERSION_DEFAULT),
        updated_at=updated_at,
    )


def write_ocr_settings(
    session: Session,
    values: dict[str, Any],
    *,
    updated_by: int | None,
) -> None:
    """Écrit (upsert) les clés fournies. Ne committe pas : la transaction est à l'appelant.

    L'enqueue de `reclassify_ocr` qui suit doit vivre dans la **même** transaction que
    cette écriture (§3-E.4.2) — sans quoi un seuil peut être écrit sans que personne ne
    re-projette les candidats.
    """
    now = datetime.now(UTC)
    for key, value in values.items():
        row = session.execute(
            select(AppSetting).where(AppSetting.key == key).with_for_update()
        ).scalar_one_or_none()
        if row is None:
            session.add(
                AppSetting(key=key, value={"value": value}, updated_by=updated_by, updated_at=now)
            )
        else:
            row.value = {"value": value}
            row.updated_by = updated_by
            row.updated_at = now
    session.flush()
