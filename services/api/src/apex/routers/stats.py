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
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Security
from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import Session

from apex.db import get_db
from apex.models.media import Media, MediaEngagement
from apex.routers._common import bearer_scheme
from apex.schemas.stats import AutoAttachRate
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
    from_: str | None = None,
    to: str | None = None,
    db: Session = Depends(get_db),
) -> AutoAttachRate:
    date_from = _parse_date(from_, "from_")
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

    row = db.execute(
        select(
            func.count(),
            func.count().filter(and_(any_link, ~human_link)),
            func.count().filter(
                or_(
                    and_(any_link, human_link),
                    and_(~any_link, Media.attachment_source == "human"),
                )
            ),
            func.count().filter(
                and_(
                    ~any_link,
                    Media.shooting_id.is_not(None),
                    Media.attachment_source == "pipeline_time",
                )
            ),
            func.count().filter(Media.shooting_id.is_(None)),
        )
        .select_from(Media)
        .where(and_(*conditions))
    ).one()

    total, auto_ocr, human, auto_time, unattached = (int(value) for value in row)
    rate = ((auto_time + auto_ocr) / total) if total else 0.0
    return AutoAttachRate(
        total=total,
        auto_time=auto_time,
        auto_ocr=auto_ocr,
        human=human,
        unattached=unattached,
        rate=round(rate, 4),
    )
