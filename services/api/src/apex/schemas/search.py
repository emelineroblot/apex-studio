"""Schémas de recherche à facettes (J2, §3-K du plan)."""

from typing import Literal

from pydantic import BaseModel

from apex.schemas.media import MediaSummary

SeriesMode = Literal["collapsed", "all"]
SortMode = Literal["shot_at", "-shot_at"]


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
