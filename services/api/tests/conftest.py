"""Fixtures de test (§3-D du plan) — base réelle `apex_test`, stockage local réel.

**Aucun mock de base de données ni de stockage** (§5 du plan) : Postgres réel
(`postgresql+psycopg://apex:apex@localhost:55433/apex_test`), `LocalDiskStorage` sur un
répertoire temporaire jetable.

**Écart documenté à l'Option 2 de la Décision D** (« chaque test dans une transaction
annulée ») : le code applicatif committe explicitement (`db.commit()` dans les routeurs,
`session.commit()` dans `queue/runner.py`) et `queue.runner.drain()` gère ses **propres**
sessions/connexions — nécessaire pour que le test de concurrence (§3-E.4, 8 threads) utilise
des connexions réellement indépendantes. Une session unique partagée par SAVEPOINT
(le motif recommandé pour « transaction annulée ») est incompatible avec ce design : un
`session.close()` interne à `drain()` invaliderait la session de test au premier appel.
**Compromis retenu** : isolation par `TRUNCATE ... RESTART IDENTITY CASCADE` après chaque
test plutôt que par rollback — plus lent, mais correct vis-à-vis des commits internes et
du multi-session. À signaler en revue.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = "postgresql+psycopg://apex:apex@localhost:55433/apex_test"

# Doit être posé AVANT tout import de `apex.config` (Settings est mis en cache via
# `lru_cache` dès le premier import) — sinon les tests tapent la base de dev par erreur.
# `APP_ENV=local` : depuis le correctif fail-closed (revue J1, suivi du bloquant n°5),
# `app_env` vaut `"production"` par défaut — sans cette ligne, `Settings()` refuserait de
# démarrer ici même (aucun `JWT_SECRET`/`WORKER_SECRET` "propre" n'est posé ci-dessous,
# ce sont volontairement des valeurs de test, pas des secrets de production).
os.environ.setdefault("APP_ENV", "local")
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("WORKER_SECRET", "test-worker-secret")
os.environ.setdefault("STORAGE_BACKEND", "local")
_TEST_STORAGE_DIR = tempfile.mkdtemp(prefix="apex-test-storage-")
os.environ.setdefault("STORAGE_LOCAL_DIR", _TEST_STORAGE_DIR)

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import MetaData, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import apex.queue.handlers  # noqa: E402,F401 — charge les handlers dans le registre
from apex.config import settings  # noqa: E402
from apex.db import SessionLocal, engine  # noqa: E402
from apex.main import app  # noqa: E402
from apex.models.user import AppUser  # noqa: E402
from apex.security import create_access_token, hash_password  # noqa: E402


def _alembic_config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return cfg


@pytest.fixture(scope="session", autouse=True)
def _migrated_test_database() -> None:
    """Base recréée une fois par session de test (§3-D, « environnement jetable »)."""
    assert settings.database_url == TEST_DATABASE_URL, (
        "Les tests doivent cibler apex_test — jamais la base de dev. "
        f"DATABASE_URL actuel : {settings.database_url}"
    )
    # `DROP SCHEMA ... CASCADE` plutôt que `alembic downgrade base` : robuste à un
    # `alembic_version` désynchronisé d'un run précédent interrompu (reproduit en
    # conditions réelles — `downgrade base` devient un no-op silencieux si la table de
    # version est vide alors que le schéma existe encore, et l'`upgrade head` suivant
    # échoue en `DuplicateTable`). Cohérent avec « environnement jetable » (AGENTS.md).
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    cfg = _alembic_config()
    command.upgrade(cfg, "head")
    yield
    shutil.rmtree(_TEST_STORAGE_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def _clean_database():
    """Isolation entre tests par `TRUNCATE` (voir écart documenté en tête de module)."""
    yield
    with engine.begin() as conn:
        meta = MetaData()
        meta.reflect(bind=conn)
        if meta.sorted_tables:
            names = ", ".join(f'"{t.name}"' for t in meta.sorted_tables)
            conn.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db_session() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> TestClient:
    # Sans `with` : ne déclenche pas le `startup` (bootstrap des comptes démo) — chaque
    # test contrôle explicitement les utilisateurs qu'il crée (stack-pitfalls, FastAPI).
    return TestClient(app)


def make_user(
    session: Session, *, role: str = "owner", email: str | None = None, full_name: str = "Test User"
) -> AppUser:
    user = AppUser(
        email=email or f"{role}-{os.urandom(4).hex()}@apex-test.dev",
        password_hash=hash_password("Test1234!"),
        full_name=full_name,
        role=role,
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def auth_headers(user: AppUser) -> dict[str, str]:
    token, _ = create_access_token(user)
    return {"Authorization": f"Bearer {token}"}
