"""Recherche à facettes en PostgreSQL natif (§3-K.2 du plan, Décision K) — construction des
prédicats, agrégats de facettes, pagination keyset, mesure du temps de réponse.

## La règle de justesse (§3-K.2)

Le compteur d'une facette **multi-sélection** (case à cocher : client, shooting, écurie,
pilote, numéro, circuit, boîtier, objectif, statut) s'évalue en appliquant **tous les
filtres actifs sauf le sien** — sinon cocher une écurie ferait tomber les autres écuries à
zéro et le filtre deviendrait inutilisable en pratique. Les facettes **mono-sélection**
(plage de dates, plage d'ISO, plage de focale) s'évaluent sur le jeu filtré **complet**,
leur propre filtre inclus.

## Un choix assumé, différent du squelette SQL du plan

Le §3-K.2 esquisse une seule CTE `filtered` réutilisée pour toutes les facettes via
`GROUPING SETS` — un raccourci pédagogique qui, pris au pied de la lettre, **viole la règle
« sauf soi »** dès qu'un filtre multi-sélection est actif (les compteurs des autres options
de cette même facette tomberaient à zéro). Ce module calcule, pour **chaque** facette
multi-sélection, son propre jeu filtré « sauf elle-même » : c'est plus de requêtes (9 petits
agrégats indexés plutôt que 3 à 5 requêtes fusionnées) mais c'est la seule façon de tenir la
garantie de justesse dans tous les cas — y compris quand une facette *inactive* devient
active. Chaque requête reste un agrégat sur un sous-ensemble indexé de `media_search`
(≤ ~8000 lignes, § Décision N) : le budget mesuré (`tests/search/test_perf.py`,
`docs/search-perf.md`) tranche s'il faut fusionner plus tard — écart documenté plutôt que
silencieux.
"""

from __future__ import annotations

import base64
import json
import time
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from fastapi import HTTPException
from sqlalchemy import ColumnElement, Float, Select, cast, func, or_, select
from sqlalchemy.dialects.postgresql import array as pg_array
from sqlalchemy.orm import Session

from apex.models.catalog import Camera, Circuit, Client, Driver, Team
from apex.models.media import MediaSeries
from apex.models.search import MediaSearch
from apex.models.shooting import Shooting
from apex.models.user import AppUser
from apex.services import access

SeriesMode = Literal["collapsed", "all"]
SortMode = Literal["shot_at", "-shot_at"]

#: Bornes ISO/focale (§3-K.2 du plan) — 5 tranches chacune, la dernière ouverte vers le haut.
ISO_BUCKET_EDGES: tuple[float, ...] = (100.0, 400.0, 1600.0, 6400.0)
FOCAL_BUCKET_EDGES: tuple[float, ...] = (24.0, 70.0, 200.0, 400.0)

#: Nombre d'options renvoyées par facette — au-delà, l'UI privilégie la recherche plein texte.
FACET_TERM_LIMIT = 50


@dataclass(slots=True)
class SearchFilters:
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
    series: SeriesMode = "collapsed"


@dataclass(slots=True)
class FacetTermRow:
    id: int
    label: str
    count: int


@dataclass(slots=True)
class FacetStatusRow:
    value: str
    count: int


@dataclass(slots=True)
class FacetBucketRow:
    from_: float | None
    to: float | None
    count: int


@dataclass(slots=True)
class FacetsResult:
    shooting: list[FacetTermRow] = field(default_factory=list)
    client: list[FacetTermRow] = field(default_factory=list)
    team: list[FacetTermRow] = field(default_factory=list)
    driver: list[FacetTermRow] = field(default_factory=list)
    car_number: list[FacetTermRow] = field(default_factory=list)
    circuit: list[FacetTermRow] = field(default_factory=list)
    camera: list[FacetTermRow] = field(default_factory=list)
    lens: list[FacetTermRow] = field(default_factory=list)
    status: list[FacetStatusRow] = field(default_factory=list)
    iso: list[FacetBucketRow] = field(default_factory=list)
    focal: list[FacetBucketRow] = field(default_factory=list)


@dataclass(slots=True)
class SearchResult:
    items: list[MediaSearch]
    series_member_counts: dict[int, int]
    facets: FacetsResult
    total: int
    next_cursor: str | None
    took_ms: float


# --- Identifiants synthétiques pour les facettes textuelles -----------------------------
# `car_number` et `lens` n'ont pas d'id numérique en base (§3-K.3 : ce sont des colonnes
# texte, pas des tables de référence) — le contrat `FacetTerm.id: int` est pourtant commun à
# toutes les facettes (gelé au lot 0, confirmé côté frontend : « le contrat impose id: int
# même pour ces deux facettes »). On expose un hash déterministe, stable d'un appel à
# l'autre : il ne sert qu'à distinguer des options, jamais à filtrer (le paramètre de requête
# `car_number`/`lens` reste la chaîne elle-même).


def synthetic_facet_id(value: str) -> int:
    return zlib.crc32(value.encode("utf-8")) & 0x7FFFFFFF


# --- Prédicats ----------------------------------------------------------------------------

_MULTI_SELECT_FACETS = (
    "shooting",
    "client",
    "team",
    "driver",
    "car_number",
    "circuit",
    "camera",
    "lens",
    "status",
)


def _facet_predicate(key: str, filters: SearchFilters) -> ColumnElement[bool] | None:
    ms = MediaSearch
    if key == "shooting":
        return ms.shooting_id.in_(filters.shooting_id) if filters.shooting_id else None
    if key == "client":
        return ms.client_id.in_(filters.client_id) if filters.client_id else None
    if key == "team":
        return ms.team_ids.overlap(filters.team_id) if filters.team_id else None
    if key == "driver":
        return ms.driver_ids.overlap(filters.driver_id) if filters.driver_id else None
    if key == "car_number":
        return ms.car_numbers.overlap(filters.car_number) if filters.car_number else None
    if key == "circuit":
        return ms.circuit_id.in_(filters.circuit_id) if filters.circuit_id else None
    if key == "camera":
        return ms.camera_id.in_(filters.camera_id) if filters.camera_id else None
    if key == "lens":
        return ms.lens_model.in_(filters.lens) if filters.lens else None
    if key == "status":
        return ms.attachment_status.in_(filters.status) if filters.status else None
    raise ValueError(f"facette inconnue : {key}")  # pragma: no cover — clés closes ci-dessus


def visibility_clause(user: AppUser) -> ColumnElement[bool] | None:
    """Même cloisonnement que `services/access.py::media_visibility_clause`, sans jointure
    à `media` — `media_search` porte déjà `shooting_id`/`uploaded_by` (§3-K.1).
    """
    if access.is_owner(user):
        return None
    return or_(
        MediaSearch.shooting_id.in_(access.visible_shooting_ids(user)),
        MediaSearch.uploaded_by == user.id,
    )


def _base_predicates(user: AppUser, filters: SearchFilters) -> list[ColumnElement[bool]]:
    """Prédicats **toujours** appliqués : jamais exclus par la règle « sauf soi », parce
    qu'ils ne sont pas des facettes multi-sélection (§3-K.2).
    """
    ms = MediaSearch
    preds: list[ColumnElement[bool]] = [ms.duplicate_of_media_id.is_(None)]
    visibility = visibility_clause(user)
    if visibility is not None:
        preds.append(visibility)
    if filters.q:
        preds.append(ms.search_vector.op("@@")(func.websearch_to_tsquery("french", filters.q)))
    if filters.iso_min is not None:
        preds.append(ms.iso >= filters.iso_min)
    if filters.iso_max is not None:
        preds.append(ms.iso <= filters.iso_max)
    if filters.focal_min is not None:
        preds.append(ms.focal_length >= filters.focal_min)
    if filters.focal_max is not None:
        preds.append(ms.focal_length <= filters.focal_max)
    if filters.date_from is not None:
        preds.append(ms.shot_at >= filters.date_from)
    if filters.date_to is not None:
        preds.append(ms.shot_at <= filters.date_to)
    if filters.series == "collapsed":
        preds.append(ms.is_series_representative.is_(True))
    return preds


def _predicates_except(
    user: AppUser, filters: SearchFilters, *, excluding: str | None
) -> list[ColumnElement[bool]]:
    preds = _base_predicates(user, filters)
    for key in _MULTI_SELECT_FACETS:
        if key == excluding:
            continue
        pred = _facet_predicate(key, filters)
        if pred is not None:
            preds.append(pred)
    return preds


def _fully_filtered_predicates(user: AppUser, filters: SearchFilters) -> list[ColumnElement[bool]]:
    return _predicates_except(user, filters, excluding=None)


# --- Curseur keyset `(shot_at, media_id)`, encodé en base64 (§3-K.2) ----------------------


def _encode_cursor(shot_at: datetime | None, media_id: int) -> str:
    payload = {"t": shot_at.isoformat() if shot_at else None, "id": media_id}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime | None, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw)
        shot_at = datetime.fromisoformat(payload["t"]) if payload.get("t") else None
        media_id = int(payload["id"])
        return shot_at, media_id
    except Exception as exc:  # noqa: BLE001 — toute forme invalide devient un 400 uniforme
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_cursor", "message": "Curseur invalide.", "detail": None},
        ) from exc


def _keyset_predicate(
    sort: SortMode, shot_at: datetime | None, media_id: int
) -> ColumnElement[bool]:
    """Condition « page suivante » pour `ORDER BY shot_at {DESC|ASC} NULLS LAST, media_id …`.

    Les `NULL` (média sans `shot_at` exploitable) sont ordonnés **après** toute date connue,
    dans les deux sens de tri — une partition entièrement postérieure au curseur tant que
    celui-ci porte une date, triée par `media_id` seul une fois qu'on y est entré.
    """
    ms = MediaSearch
    if sort == "-shot_at":
        if shot_at is None:
            return ms.shot_at.is_(None) & (ms.media_id < media_id)
        return (
            (ms.shot_at.is_not(None) & (ms.shot_at < shot_at))
            | ((ms.shot_at == shot_at) & (ms.media_id < media_id))
            | ms.shot_at.is_(None)
        )
    if shot_at is None:
        return ms.shot_at.is_(None) & (ms.media_id > media_id)
    return (
        (ms.shot_at.is_not(None) & (ms.shot_at > shot_at))
        | ((ms.shot_at == shot_at) & (ms.media_id > media_id))
        | ms.shot_at.is_(None)
    )


def _order_by(stmt: Select[Any], sort: SortMode) -> Select[Any]:
    ms = MediaSearch
    if sort == "-shot_at":
        return stmt.order_by(ms.shot_at.desc().nulls_last(), ms.media_id.desc())
    return stmt.order_by(ms.shot_at.asc().nulls_last(), ms.media_id.asc())


# --- Agrégats de facettes -------------------------------------------------------------


def _label_lookup(session: Session, model: Any, name_col: Any, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = session.execute(select(model.id, name_col).where(model.id.in_(ids))).all()
    return {int(row[0]): str(row[1]) for row in rows}


def _scalar_facet(
    session: Session,
    user: AppUser,
    filters: SearchFilters,
    *,
    key: str,
    column: Any,
) -> list[tuple[int, int]]:
    preds = _predicates_except(user, filters, excluding=key)
    rows = session.execute(
        select(column, func.count())
        .select_from(MediaSearch)
        .where(*preds, column.is_not(None))
        .group_by(column)
        .order_by(func.count().desc())
        .limit(FACET_TERM_LIMIT)
    ).all()
    return [(int(row[0]), int(row[1])) for row in rows]


def _array_facet(
    session: Session,
    user: AppUser,
    filters: SearchFilters,
    *,
    key: str,
    column: Any,
) -> list[tuple[Any, int]]:
    """`unnest()` en tant que fonction table (jointure implicite corrélée, idiome Postgres
    pour dépiler un tableau) — pas de bricolage de SQL brut, juste l'API `table_valued` de
    SQLAlchemy 2.0 pour un cas que le langage d'expression ne modélise pas nativement.
    """
    preds = _predicates_except(user, filters, excluding=key)
    # `.render_derived()` **requis** : sans lui, SQLAlchemy référence `anon_1.v` dans le
    # SELECT mais rend `unnest(...) AS anon_1` sans la liste de colonnes dérivées — Postgres
    # nomme alors la colonne d'après la fonction (`unnest`), pas `v`, et lève
    # `UndefinedColumn: anon_1.v` (reproduit en conditions réelles). `.render_derived()`
    # force le rendu `AS anon_1(v)` qui donne son nom à la colonne.
    unnested = func.unnest(column).table_valued("v", joins_implicitly=True).render_derived()
    stmt = (
        select(unnested.c.v, func.count())
        .select_from(MediaSearch)
        .where(*preds)
        .group_by(unnested.c.v)
        .order_by(func.count().desc())
        .limit(FACET_TERM_LIMIT)
    )
    rows = session.execute(stmt).all()
    return [(row[0], int(row[1])) for row in rows]


def _status_facet(session: Session, user: AppUser, filters: SearchFilters) -> list[FacetStatusRow]:
    preds = _predicates_except(user, filters, excluding="status")
    rows = session.execute(
        select(MediaSearch.attachment_status, func.count())
        .select_from(MediaSearch)
        .where(*preds)
        .group_by(MediaSearch.attachment_status)
        .order_by(func.count().desc())
    ).all()
    return [FacetStatusRow(value=str(row[0]), count=int(row[1])) for row in rows]


def _histogram(
    session: Session,
    user: AppUser,
    filters: SearchFilters,
    *,
    column: Any,
    edges: tuple[float, ...],
) -> list[FacetBucketRow]:
    """Mono-sélection (§3-K.2) : jeu filtré **complet**, propre filtre inclus."""
    preds = _fully_filtered_predicates(user, filters)
    operand = cast(column, Float)
    bucket_expr = func.width_bucket(operand, pg_array(edges))
    stmt = (
        select(bucket_expr.label("bucket"), func.count())
        .select_from(MediaSearch)
        .where(*preds, column.is_not(None))
        .group_by(bucket_expr)
        .order_by(bucket_expr)
    )
    rows = session.execute(stmt).all()
    bounds: list[float | None] = [None, *edges, None]
    result: list[FacetBucketRow] = []
    for bucket_index, count in rows:
        idx = int(bucket_index)
        lo = bounds[idx] if 0 <= idx < len(bounds) else None
        hi = bounds[idx + 1] if 0 <= idx + 1 < len(bounds) else None
        result.append(FacetBucketRow(from_=lo, to=hi, count=int(count)))
    return result


def _build_facets(session: Session, user: AppUser, filters: SearchFilters) -> FacetsResult:
    shooting_counts = _scalar_facet(
        session, user, filters, key="shooting", column=MediaSearch.shooting_id
    )
    client_counts = _scalar_facet(
        session, user, filters, key="client", column=MediaSearch.client_id
    )
    circuit_counts = _scalar_facet(
        session, user, filters, key="circuit", column=MediaSearch.circuit_id
    )
    camera_counts = _scalar_facet(
        session, user, filters, key="camera", column=MediaSearch.camera_id
    )

    lens_preds = _predicates_except(user, filters, excluding="lens")
    lens_rows = session.execute(
        select(MediaSearch.lens_model, func.count())
        .select_from(MediaSearch)
        .where(*lens_preds, MediaSearch.lens_model.is_not(None))
        .group_by(MediaSearch.lens_model)
        .order_by(func.count().desc())
        .limit(FACET_TERM_LIMIT)
    ).all()

    team_counts = _array_facet(session, user, filters, key="team", column=MediaSearch.team_ids)
    driver_counts = _array_facet(
        session, user, filters, key="driver", column=MediaSearch.driver_ids
    )
    car_number_counts = _array_facet(
        session, user, filters, key="car_number", column=MediaSearch.car_numbers
    )

    shooting_labels = _label_lookup(
        session, Shooting, Shooting.title, {i for i, _ in shooting_counts}
    )
    client_labels = _label_lookup(session, Client, Client.name, {i for i, _ in client_counts})
    circuit_labels = _label_lookup(session, Circuit, Circuit.name, {i for i, _ in circuit_counts})
    camera_labels = _label_lookup(session, Camera, Camera.model, {i for i, _ in camera_counts})
    team_labels = _label_lookup(session, Team, Team.name, {int(i) for i, _ in team_counts})
    driver_labels = _label_lookup(
        session, Driver, Driver.full_name, {int(i) for i, _ in driver_counts}
    )

    def _camera_label(camera_id: int) -> str:
        label = camera_labels.get(camera_id)
        return label or f"Boîtier #{camera_id}"

    return FacetsResult(
        shooting=[
            FacetTermRow(id=i, label=shooting_labels.get(i, f"Shooting #{i}"), count=c)
            for i, c in shooting_counts
        ],
        client=[
            FacetTermRow(id=i, label=client_labels.get(i, f"Client #{i}"), count=c)
            for i, c in client_counts
        ],
        team=[
            FacetTermRow(id=int(i), label=team_labels.get(int(i), f"Écurie #{i}"), count=c)
            for i, c in team_counts
        ],
        driver=[
            FacetTermRow(id=int(i), label=driver_labels.get(int(i), f"Pilote #{i}"), count=c)
            for i, c in driver_counts
        ],
        car_number=[
            FacetTermRow(id=synthetic_facet_id(str(v)), label=str(v), count=c)
            for v, c in car_number_counts
        ],
        circuit=[
            FacetTermRow(id=i, label=circuit_labels.get(i, f"Circuit #{i}"), count=c)
            for i, c in circuit_counts
        ],
        camera=[FacetTermRow(id=i, label=_camera_label(i), count=c) for i, c in camera_counts],
        lens=[
            FacetTermRow(id=synthetic_facet_id(str(row[0])), label=str(row[0]), count=int(row[1]))
            for row in lens_rows
        ],
        status=_status_facet(session, user, filters),
        iso=_histogram(session, user, filters, column=MediaSearch.iso, edges=ISO_BUCKET_EDGES),
        focal=_histogram(
            session, user, filters, column=MediaSearch.focal_length, edges=FOCAL_BUCKET_EDGES
        ),
    )


# --- Orchestrateur -------------------------------------------------------------------


def run_search(
    session: Session,
    user: AppUser,
    filters: SearchFilters,
    *,
    sort: SortMode,
    cursor: str | None,
    limit: int,
) -> SearchResult:
    started = time.perf_counter()

    preds = _fully_filtered_predicates(user, filters)
    total = int(
        session.execute(
            select(func.count()).select_from(select(MediaSearch.media_id).where(*preds).subquery())
        ).scalar_one()
    )

    stmt = select(MediaSearch).where(*preds)
    if cursor is not None:
        cursor_shot_at, cursor_media_id = _decode_cursor(cursor)
        stmt = stmt.where(_keyset_predicate(sort, cursor_shot_at, cursor_media_id))
    stmt = _order_by(stmt, sort).limit(limit + 1)

    rows = list(session.execute(stmt).scalars().all())
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = (
        _encode_cursor(items[-1].shot_at, items[-1].media_id) if has_more and items else None
    )

    series_ids = {item.series_id for item in items if item.series_id is not None}
    series_member_counts: dict[int, int] = {}
    if series_ids:
        member_rows = session.execute(
            select(MediaSeries.id, MediaSeries.member_count).where(MediaSeries.id.in_(series_ids))
        ).all()
        series_member_counts = {int(sid): int(count) for sid, count in member_rows}

    facets = _build_facets(session, user, filters)
    took_ms = (time.perf_counter() - started) * 1000

    return SearchResult(
        items=items,
        series_member_counts=series_member_counts,
        facets=facets,
        total=total,
        next_cursor=next_cursor,
        took_ms=took_ms,
    )


def collect_media_ids(session: Session, user: AppUser, filters: SearchFilters) -> list[int]:
    """Tous les `media_id` du jeu filtré, sans pagination — composition d'une collection
    « depuis cette recherche » (`POST /collections/{id}/items {from_search: …}`, §3-K).
    Ordonné par `media_id` pour rester déterministe d'un appel à l'autre.
    """
    preds = _fully_filtered_predicates(user, filters)
    rows = session.execute(
        select(MediaSearch.media_id).where(*preds).order_by(MediaSearch.media_id)
    ).scalars()
    return [int(r) for r in rows]
