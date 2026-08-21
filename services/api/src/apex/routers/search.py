"""`GET /search` — recherche à facettes en PostgreSQL natif (J2, §3-K).

Toute la logique vit dans `services/facets.py` : ce routeur ne fait que parser les
paramètres de requête, appeler `run_search()` et mettre en forme la réponse — `took_ms` est
mesuré côté serveur par `facets.run_search` et **répercuté tel quel** (critère d'acceptation
« temps de réponse mesuré et documenté », §3-K.2).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from sqlalchemy.orm import Session

from apex.db import get_db
from apex.routers._common import bearer_scheme
from apex.schemas.media import MediaSummary
from apex.schemas.search import FacetBucket, Facets, FacetStatusTerm, FacetTerm, SearchResponse
from apex.security import CurrentUser
from apex.services.facets import SearchFilters, SeriesMode, SortMode, run_search

router = APIRouter(tags=["search"], dependencies=[Security(bearer_scheme)])


def _parse_datetime(value: str | None, *, param: str) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_datetime",
                "message": f"Paramètre « {param} » : date/heure ISO 8601 attendue.",
                "detail": {"param": param, "value": value},
            },
        ) from exc


def _thumb_url(media_id: int) -> str:
    return f"/media/{media_id}/file/thumb"


@router.get("/search", response_model=SearchResponse, summary="Recherche à facettes")
def search(
    user: CurrentUser,
    db: Session = Depends(get_db),
    q: str | None = None,
    shooting_id: list[int] | None = Query(default=None),
    client_id: list[int] | None = Query(default=None),
    team_id: list[int] | None = Query(default=None),
    driver_id: list[int] | None = Query(default=None),
    car_number: list[str] | None = Query(default=None),
    circuit_id: list[int] | None = Query(default=None),
    camera_id: list[int] | None = Query(default=None),
    lens: list[str] | None = Query(default=None),
    iso_min: int | None = None,
    iso_max: int | None = None,
    focal_min: float | None = None,
    focal_max: float | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status: list[str] | None = Query(default=None),
    series: SeriesMode = "collapsed",
    sort: SortMode = "-shot_at",
    cursor: str | None = None,
    limit: int = Query(default=50, le=100),
) -> SearchResponse:
    filters = SearchFilters(
        q=q,
        shooting_id=shooting_id,
        client_id=client_id,
        team_id=team_id,
        driver_id=driver_id,
        car_number=car_number,
        circuit_id=circuit_id,
        camera_id=camera_id,
        lens=lens,
        iso_min=iso_min,
        iso_max=iso_max,
        focal_min=focal_min,
        focal_max=focal_max,
        date_from=_parse_datetime(date_from, param="date_from"),
        date_to=_parse_datetime(date_to, param="date_to"),
        status=status,
        series=series,
    )
    result = run_search(db, user, filters, sort=sort, cursor=cursor, limit=limit)

    items = [
        MediaSummary(
            id=row.media_id,
            thumb_url=_thumb_url(row.media_id),
            shot_at=row.shot_at,
            ingest_status=row.ingest_status,
            attachment_status=row.attachment_status,
            shooting_id=row.shooting_id,
            is_simulated=row.is_simulated,
            duplicate_of_media_id=row.duplicate_of_media_id,
            series_id=row.series_id,
            series_member_count=(
                result.series_member_counts.get(row.series_id) if row.series_id else None
            ),
        )
        for row in result.items
    ]

    facets = Facets(
        shooting=[FacetTerm(id=f.id, label=f.label, count=f.count) for f in result.facets.shooting],
        client=[FacetTerm(id=f.id, label=f.label, count=f.count) for f in result.facets.client],
        team=[FacetTerm(id=f.id, label=f.label, count=f.count) for f in result.facets.team],
        driver=[FacetTerm(id=f.id, label=f.label, count=f.count) for f in result.facets.driver],
        car_number=[
            FacetTerm(id=f.id, label=f.label, count=f.count) for f in result.facets.car_number
        ],
        circuit=[FacetTerm(id=f.id, label=f.label, count=f.count) for f in result.facets.circuit],
        camera=[FacetTerm(id=f.id, label=f.label, count=f.count) for f in result.facets.camera],
        lens=[FacetTerm(id=f.id, label=f.label, count=f.count) for f in result.facets.lens],
        status=[FacetStatusTerm(value=f.value, count=f.count) for f in result.facets.status],
        iso=[FacetBucket(from_=b.from_, to=b.to, count=b.count) for b in result.facets.iso],
        focal=[FacetBucket(from_=b.from_, to=b.to, count=b.count) for b in result.facets.focal],
    )

    return SearchResponse(
        items=items,
        facets=facets,
        total=result.total,
        next_cursor=result.next_cursor,
        took_ms=round(result.took_ms, 2),
    )
