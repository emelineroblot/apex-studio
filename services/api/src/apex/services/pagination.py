"""Pagination par curseur (keyset), jamais `OFFSET` (cohérent avec §3-K.2 du plan, qui
prescrit la même règle pour la recherche à facettes). Le curseur opaque est simplement
l'`id` du dernier élément vu — suffisant tant que le tri est stable sur une colonne `id`
strictement croissante (`BIGINT GENERATED ALWAYS AS IDENTITY`, jamais réutilisé).
"""

from __future__ import annotations

from typing import Any, TypeVar

from fastapi import HTTPException
from sqlalchemy import Select
from sqlalchemy.orm import InstrumentedAttribute, Session

T = TypeVar("T")


def paginate_by_id(
    session: Session,
    stmt: Select[Any],
    id_column: InstrumentedAttribute[int],
    *,
    cursor: str | None,
    limit: int,
) -> tuple[list[Any], str | None]:
    """Applique curseur + `limit+1` à `stmt` (déjà filtrée), renvoie `(items, next_cursor)`."""
    if cursor is not None:
        try:
            after_id = int(cursor)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_cursor", "message": "Curseur invalide.", "detail": None},
            ) from exc
        stmt = stmt.where(id_column > after_id)

    stmt = stmt.order_by(id_column).limit(limit + 1)
    rows = list(session.execute(stmt).scalars().all())

    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = str(id_column_value(items[-1], id_column)) if has_more and items else None
    return items, next_cursor


def id_column_value(row: Any, id_column: InstrumentedAttribute[int]) -> int:
    """Lit la valeur de la colonne id sur une ligne ORM — la colonne porte son nom Python."""
    key = id_column.key
    assert key is not None
    return int(getattr(row, key))
