"""File de tâches en table PostgreSQL (§3-E du plan) — pièce technique centrale.

`job_execution_log` n'est pas un besoin métier : elle sert de preuve de non-double-
traitement pour `tests/queue/test_concurrency.py` (contrainte `UNIQUE(job_id)`).
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    desc,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apex.models.base import Base

JOB_STATUSES = ("pending", "running", "done", "failed", "dead")


class Job(Base):
    __tablename__ = "job"
    __table_args__ = (
        CheckConstraint(f"status IN {JOB_STATUSES}", name="status_valid"),
        # Index de réclamation : partiel, ne couvre que la file réellement en attente (§3-E.1).
        Index(
            "job_claim_idx",
            "priority",
            "run_at",
            "id",
            postgresql_where=text("status = 'pending'"),
        ),
        # Anti-doublon d'enqueue : au plus un job `pending` par (kind, dedupe_key).
        # Correction revue J1 (🟠, `queue/enqueue.py`) : ne couvre plus `running` — un job
        # en cours d'exécution ne doit jamais bloquer l'enqueue d'un successeur, sous peine
        # de perdre silencieusement un signal de recalcul (`finalize_batch` bloqué en
        # `processing`, cf. docstring d'`enqueue.py`).
        Index(
            "job_dedupe_idx",
            "kind",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL AND status = 'pending'"),
        ),
        # Détection des jobs orphelins après crash.
        Index(
            "job_stale_idx",
            "heartbeat_at",
            postgresql_where=text("status = 'running'"),
        ),
        Index("job_recent_idx", desc("created_at")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    dedupe_key: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="100")
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    locked_by: Mapped[str | None] = mapped_column(Text)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class JobExecutionLog(Base):
    """Preuve de non-double-traitement (§3-E.4) — un log par exécution réellement menée."""

    __tablename__ = "job_execution_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("job.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    worker_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
