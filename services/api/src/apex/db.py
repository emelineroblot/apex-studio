"""Connexion base de données — SQLAlchemy 2.0 **synchrone** via psycopg 3 (Décision B).

Le worker est CPU-bound (Pillow, numpy, ONNX en J2) : l'async n'apporte rien et complique
`SKIP LOCKED`. FastAPI exécute les endpoints `def` (non-`async`) dans un threadpool.
Pool volontairement petit (`pool_size=2, max_overflow=3`) — contrainte des connexions en
environnement serverless (Neon).
"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from apex.config import settings

engine = create_engine(
    settings.database_url,
    pool_size=2,
    max_overflow=3,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session]:
    """Dépendance FastAPI : une session par requête, fermée systématiquement."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session]:
    """Contexte pour le code hors requête HTTP (worker, CLI, seed)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
