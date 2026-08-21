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
from sqlalchemy.pool import NullPool

from apex.config import settings

engine = create_engine(
    settings.database_url,
    pool_size=2,
    max_overflow=3,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

# Moteur dédié au heartbeat (`queue/claim.py::heartbeat`, revue J2, 🔴 n°2) — **jamais**
# `engine` ci-dessus : sous charge concurrente (plusieurs workers, un heartbeat par job
# traité), partager le même `QueuePool` de 2+3 connexions avec les sessions applicatives
# provoque des `QueuePool limit ... timeout` (reproduit par
# `tests/queue/test_concurrency.py`, 8 workers). `NullPool` : chaque heartbeat ouvre puis
# referme sa propre connexion physique, sans jamais disputer le pool applicatif — le budget
# de connexions Neon (dette documentée, `AGENTS.md`/plan §3-C) reste à surveiller au premier
# déploiement, mais un heartbeat est bref (un `UPDATE` d'une ligne) et peu fréquent par
# rapport au trafic applicatif.
heartbeat_engine = create_engine(settings.database_url, poolclass=NullPool, future=True)


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
