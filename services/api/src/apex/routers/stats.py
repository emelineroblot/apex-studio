"""`GET /stats/auto-attach-rate` (J2) — **taux de rattachement automatique**.

Ce n'est pas une métrique cachée : c'est un indicateur produit, affiché au dashboard, et
publié dans l'étude de cas. Il répond à « quelle proportion des photos a trouvé sa place
sans qu'un humain ait à intervenir ? ».

Définitions volontairement explicites — un taux dont on ne sait pas ce qu'il compte ne vaut
rien :

| Champ | Ce qu'on compte |
|---|---|
| `total` | Médias ingérés, hors doublons exacts (un doublon n'est pas un travail de plus) |
| `auto_ocr` | Rattaché à ≥ 1 engagement **par l'OCR seul** — aucun de ses rattachements n'a été touché par un humain |
| `human` | Rattaché avec une intervention humaine (rattachement manuel, ou arbitrage en file de validation) |
| `auto_time` | Aucun engagement, mais rattaché à un shooting par la **fenêtre temporelle** seule |
| `unattached` | Ni engagement, ni shooting — le bac « à rattacher » |
| `rate` | `(auto_time + auto_ocr) / total` |

Une photo arbitrée en file de validation compte donc en `human`, **pas** en automatique :
c'est précisément ce que ce taux doit mesurer. Y compter les validations humaines
reviendrait à se mentir sur la seule métrique que le produit expose.

## Ventilation réel / simulé (revue J2, 🟠 n°1, §3-N.1 du plan)

Les champs de tête (`total`, `auto_time`, …, `rate`) restent l'agrégat **toutes origines
confondues** — rétrocompatible avec la forme d'origine du contrat. `real` et `simulated`
portent le **même** calcul, restreint par `media.is_simulated`. Sur le jeu de démonstration
(§ Décision N.1 du plan), `simulated` porte l'écrasante majorité du volume (~8 400 médias) et
`real` une poignée (`demo-photos/`) : un tableau de bord qui n'affiche que l'agrégat donnerait
l'illusion d'un traitement réel à grande échelle. Une seule requête SQL (`FILTER` par
population) — pas de round-trip supplémentaire.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from sqlalchemy import ColumnElement, and_, func, or_, select, true
from sqlalchemy.orm import Session

from apex.db import get_db
from apex.models.media import Media, MediaEngagement
from apex.routers._common import bearer_scheme
from apex.schemas.stats import AutoAttachRate, AutoAttachRatePopulation
from apex.security import CurrentUser
from apex.services import access

router = APIRouter(prefix="/stats", tags=["stats"], dependencies=[Security(bearer_scheme)])


def _parse_date(value: str | None, field: str) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_date",
                "message": f"« {field} » n'est pas une date ISO 8601 valide.",
                "detail": {"value": value},
            },
        ) from exc


def _has_link(*extra: ColumnElement[bool]) -> ColumnElement[bool]:
    """`EXISTS` : ce média porte-t-il un rattachement répondant à `extra` ?"""
    return (
        select(MediaEngagement.media_id)
        .where(MediaEngagement.media_id == Media.id, *extra)
        .exists()
    )


@router.get(
    "/auto-attach-rate", response_model=AutoAttachRate, summary="Taux de rattachement automatique"
)
def auto_attach_rate(
    user: CurrentUser,
    shooting_id: int | None = None,
    # `from` est un mot réservé Python : le paramètre Python reste `from_`, mais le contrat
    # public expose `from` (§ pièges projet, même convention que `shootings.py::list_shootings`
    # — ne plus fuir un détail d'implémentation Python dans l'API publique, point de contrat
    # signalé par l'agent frontend J2).
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    db: Session = Depends(get_db),
) -> AutoAttachRate:
    date_from = _parse_date(from_, "from")
    date_to = _parse_date(to, "to")

    conditions: list[ColumnElement[bool]] = [
        Media.ingest_status == "ingested",
        Media.duplicate_of_media_id.is_(None),
    ]
    visibility = access.media_visibility_clause(user)
    if visibility is not None:
        conditions.append(visibility)
    if shooting_id is not None:
        conditions.append(Media.shooting_id == shooting_id)
    if date_from is not None:
        conditions.append(Media.shot_at >= date_from)
    if date_to is not None:
        conditions.append(Media.shot_at <= date_to)

    any_link = _has_link()
    # Un humain est passé par là : soit il a rattaché à la main (`source='human'`), soit il
    # a validé une proposition de l'OCR en file (`created_by` renseigné par la projection).
    human_link = _has_link(
        or_(MediaEngagement.source == "human", MediaEngagement.created_by.is_not(None))
    )

    def _counts(scope: ColumnElement[bool]) -> tuple[Any, Any, Any, Any, Any]:
        """5 agrégats `FILTER`, restreints à `scope` — réutilisé pour l'agrégat toutes
        origines confondues (`true()`) et pour chaque population (`is_simulated` = / ≠).
        """
        return (
            func.count().filter(scope),
            func.count().filter(and_(scope, any_link, ~human_link)),
            func.count().filter(
                and_(
                    scope,
                    or_(
                        and_(any_link, human_link),
                        and_(~any_link, Media.attachment_source == "human"),
                    ),
                )
            ),
            func.count().filter(
                and_(
                    scope,
                    ~any_link,
                    Media.shooting_id.is_not(None),
                    Media.attachment_source == "pipeline_time",
                )
            ),
            func.count().filter(and_(scope, Media.shooting_id.is_(None))),
        )

    row = db.execute(
        select(
            *_counts(true()),
            *_counts(Media.is_simulated.is_(False)),
            *_counts(Media.is_simulated.is_(True)),
        )
        .select_from(Media)
        .where(and_(*conditions))
    ).one()

    values = [int(value) for value in row]
    all_counts, real_counts, simulated_counts = values[0:5], values[5:10], values[10:15]

    def _rate(auto_time: int, auto_ocr: int, total: int) -> float:
        return round(((auto_time + auto_ocr) / total), 4) if total else 0.0

    def _population(counts: list[int]) -> AutoAttachRatePopulation:
        total, auto_ocr, human, auto_time, unattached = counts
        return AutoAttachRatePopulation(
            total=total,
            auto_time=auto_time,
            auto_ocr=auto_ocr,
            human=human,
            unattached=unattached,
            rate=_rate(auto_time, auto_ocr, total),
        )

    total, auto_ocr, human, auto_time, unattached = all_counts
    return AutoAttachRate(
        total=total,
        auto_time=auto_time,
        auto_ocr=auto_ocr,
        human=human,
        unattached=unattached,
        rate=_rate(auto_time, auto_ocr, total),
        real=_population(real_counts),
        simulated=_population(simulated_counts),
    )
