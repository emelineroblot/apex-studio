"""`GET /search` — recherche à facettes en PostgreSQL natif (J2, §3-K). Logique en Lot
`services/facets.py` (hors lot 0)."""

from fastapi import APIRouter, Query, Security

from apex.routers._common import bearer_scheme, not_implemented
from apex.schemas.search import SearchResponse, SeriesMode, SortMode

router = APIRouter(tags=["search"], dependencies=[Security(bearer_scheme)])


@router.get("/search", response_model=SearchResponse, summary="Recherche à facettes")
def search(
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
    not_implemented("GET /search")
