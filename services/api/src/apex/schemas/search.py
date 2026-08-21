"""Schémas de recherche à facettes (J2, §3-K du plan)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from apex.schemas.media import MediaSummary

SeriesMode = Literal["collapsed", "all"]
SortMode = Literal["shot_at", "-shot_at"]


class FromSearchFilters(BaseModel):
    """`from_search` de `POST /collections/{id}/items` — **mêmes paramètres** que
    `GET /search` (§3-K), en JSON plutôt qu'en query string.

    Revue J2 (🟡 12) : remplace un `dict[str, Any]` non validé. Un champ mal typé (ex.
    `shooting_id` envoyé comme entier plutôt que liste) levait auparavant une exception SQL
    non capturée en aval de `services/facets.py` — `500` au lieu d'un `422` Pydantic normal.
    """

    q: str | None = None
    shooting_id: list[int] | None = None
    client_id: list[int] | None = None
    team_id: list[int] | None = None
    driver_id: list[int] | None = None
    car_number: list[str] | None = None
    circuit_id: list[int] | None = None
    camera_id: list[int] | None = None
    lens: list[str] | None = None
    iso_min: int | None = None
    iso_max: int | None = None
    focal_min: float | None = None
    focal_max: float | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    status: list[str] | None = None
    #: Revue J2 (🟠 n°1) — même contrat que `GET /search?is_simulated=`.
    is_simulated: bool | None = None
    series: SeriesMode = "collapsed"


class FacetTerm(BaseModel):
    id: int
    label: str
    count: int


class FacetStatusTerm(BaseModel):
    value: str
    count: int


class FacetBucket(BaseModel):
    """Histogramme `width_bucket` (ISO, focale) — bornes métier fixées en `app_setting`."""

    from_: float | None = None
    to: float | None = None
    count: int

    model_config = {"populate_by_name": True}


class Facets(BaseModel):
    shooting: list[FacetTerm]
    client: list[FacetTerm]
    team: list[FacetTerm]
    driver: list[FacetTerm]
    car_number: list[FacetTerm]
    circuit: list[FacetTerm]
    camera: list[FacetTerm]
    lens: list[FacetTerm]
    status: list[FacetStatusTerm]
    iso: list[FacetBucket]
    focal: list[FacetBucket]


class SearchResponse(BaseModel):
    """`took_ms` mesuré côté serveur — critère d'acceptation « temps mesuré et documenté »."""

    items: list[MediaSummary]
    facets: Facets
    total: int
    next_cursor: str | None
    took_ms: float
