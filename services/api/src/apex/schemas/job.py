"""Schémas de la file de tâches — `GET /queue/stats`, `POST /jobs/tick`."""

from pydantic import BaseModel


class QueueStats(BaseModel):
    pending: int
    running: int
    dead: int
    oldest_pending_age_s: float | None
    #: Parmi `pending` : jobs que *cet* environnement ne sait pas exécuter et laisse à un
    #: worker plus capable (typiquement `ocr_media` vu depuis la fonction Vercel, qui
    #: n'embarque pas le moteur OCR). Sous-ensemble de `pending`, jamais un total à part.
    deferred: int


class TickResponse(BaseModel):
    claimed: int
    done: int
    failed: int
    remaining: int
    #: Voir `QueueStats.deferred` — ce que ce tick a délibérément laissé en file.
    deferred: int
