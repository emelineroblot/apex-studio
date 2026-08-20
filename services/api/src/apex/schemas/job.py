"""Schémas de la file de tâches — `GET /queue/stats`, `POST /jobs/tick`."""

from pydantic import BaseModel


class QueueStats(BaseModel):
    pending: int
    running: int
    dead: int
    oldest_pending_age_s: float | None


class TickResponse(BaseModel):
    claimed: int
    done: int
    failed: int
    remaining: int
