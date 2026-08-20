"""Schémas transverses : pagination, erreurs — communs aux 3 jalons."""

from typing import Any

from pydantic import BaseModel


class Page[T](BaseModel):
    """Enveloppe de pagination — keyset (curseur opaque), jamais `OFFSET` (§3-K.2)."""

    items: list[T]
    next_cursor: str | None = None
    total: int | None = None


class ErrorBody(BaseModel):
    """Corps d'erreur uniforme du contrat d'API : `{code, message, detail}`."""

    code: str
    message: str
    detail: Any | None = None
