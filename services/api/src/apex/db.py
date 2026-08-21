"""Connexion base de données — SQLAlchemy 2.0 **synchrone** via psycopg 3 (Décision B).

Le worker est CPU-bound (Pillow, numpy, ONNX en J2) : l'async n'apporte rien et complique
`SKIP LOCKED`. FastAPI exécute les endpoints `def` (non-`async`) dans un threadpool.
Pool volontairement petit (`pool_size=2, max_overflow=3`) — contrainte des connexions en
environnement serverless, où chaque invocation ouvre son propre moteur.
"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from apex.config import settings

#: Contournements imposés par le pooler Supabase (Supavisor, mode transaction — même
#: comportement que PgBouncer). Absents en local, où l'on parle directement à PostgreSQL.
_CONNECT_ARGS: dict[str, object] = {}
if settings.is_remote:
    # Les instructions préparées ne survivent pas au multiplexage des connexions : psycopg
    # en réutiliserait une posée sur une autre session backend et la requête échouerait.
    _CONNECT_ARGS["prepare_threshold"] = None

#: Supavisor ferme les connexions inactives autour de cinq minutes. Recycler un peu avant
#: évite de tirer une connexion déjà morte du pool — `pool_pre_ping` la rattraperait, au
#: prix d'un aller-retour perdu sur la première requête d'un réveil.
_POOL_RECYCLE_SECONDS = 280

#: Le pooler Supabase plafonne à **200 connexions clients pour tout le projet**, partagées
#: entre les fonctions Vercel, le worker lancé depuis un poste et le moindre `psql`. Chaque
#: instance de fonction gardait jusqu'à 2+3 connexions : quelques instances concurrentes et
#: un worker suffisaient à saturer — constaté en production (`EMAXCONN`), l'application
#: refusant alors de démarrer. Un pool minuscule par processus est la seule discipline qui
#: tienne quand on ne contrôle pas le nombre de processus.
_POOL_SIZE, _MAX_OVERFLOW = (1, 2) if settings.is_remote else (2, 3)

engine = create_engine(
    settings.database_url,
    pool_size=_POOL_SIZE,
    max_overflow=_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=_POOL_RECYCLE_SECONDS,
    connect_args=_CONNECT_ARGS,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

# Moteur dédié au heartbeat (`queue/claim.py::heartbeat`, revue J2, 🔴 n°2) — **jamais**
# `engine` ci-dessus : sous charge concurrente (plusieurs workers, un heartbeat par job
# traité), partager le même `QueuePool` de 2+3 connexions avec les sessions applicatives
# provoque des `QueuePool limit ... timeout` (reproduit par
# `tests/queue/test_concurrency.py`, 8 workers). `NullPool` : chaque heartbeat ouvre puis
# referme sa propre connexion physique, sans jamais disputer le pool applicatif — le budget
# de connexions du pooler Supabase (dette documentée, `AGENTS.md`) reste à surveiller au premier
# déploiement, mais un heartbeat est bref (un `UPDATE` d'une ligne) et peu fréquent par
# rapport au trafic applicatif.
# `NullPool` en local : chaque heartbeat ouvre puis referme sa connexion, ce qui est le
# comportement le plus simple et le plus sûr face à une base locale.
#
# **Jamais en distant.** Le worker rafraîchit le heartbeat avant *chaque* job : sur trois
# cents jobs, `NullPool` ouvre trois cents connexions physiques successives vers le pooler,
# qui les compte toutes tant qu'il ne les a pas recyclées. C'est ce qui a contribué à
# atteindre la limite de 200 en production. Un pool dédié minuscule garde la propriété
# recherchée à l'origine — ne jamais disputer les connexions du pool applicatif (revue J2,
# 🔴 n°2) — sans ouvrir une connexion par battement.
heartbeat_engine = (
    create_engine(
        settings.database_url,
        pool_size=1,
        max_overflow=1,
        pool_pre_ping=True,
        pool_recycle=_POOL_RECYCLE_SECONDS,
        connect_args=_CONNECT_ARGS,
        future=True,
    )
    if settings.is_remote
    else create_engine(
        settings.database_url, poolclass=NullPool, connect_args=_CONNECT_ARGS, future=True
    )
)


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
