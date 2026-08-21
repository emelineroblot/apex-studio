"""Application FastAPI — point d'entrée `apex.main:app`.

Sert aussi bien en local (`uvicorn apex.main:app`) qu'en serverless (`api/index.py`,
Vercel). CORS restreint à l'origine du frontend (Décision A : pas de cookie, JWT en
en-tête `Authorization`, donc pas de `credentials` à gérer).
"""

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

import apex.queue.handlers  # noqa: F401 — charge les handlers dans le registre (§3-E.3)
from apex.config import settings
from apex.db import SessionLocal, engine
from apex.demo.accounts import ensure_demo_users
from apex.routers import (
    auth,
    batches,
    billing,
    cameras,
    circuits,
    clients,
    collections,
    cron,
    dashboard,
    demo,
    drivers,
    engagements,
    jobs,
    media,
    public,
    review,
    search,
    sharing,
    shootings,
    stats,
    teams,
    users,
)
from apex.routers import settings as settings_router
from apex.services.storage import get_storage_client

API_PREFIX = "/api/v1"

app = FastAPI(
    title=f"{settings.app_name} API",
    description=(
        f"API de {settings.app_name} — pipeline d'ingestion, recherche à facettes et "
        f"espace client de {settings.studio_name}."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _error_body(code: str, message: str, detail: Any = None) -> dict[str, Any]:
    return {"code": code, "message": message, "detail": detail}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Uniformise le corps d'erreur : `{"code", "message", "detail"}` (contrat d'API)."""
    body = exc.detail
    if isinstance(body, dict) and "code" in body and "message" in body:
        payload = body
    else:
        payload = _error_body(code="http_error", message=str(body), detail=None)
    return JSONResponse(status_code=exc.status_code, content=payload, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=_error_body(
            code="validation_error",
            message="Les données envoyées sont invalides.",
            detail=exc.errors(),
        ),
    )


# Routeurs J1
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(demo.router, prefix=API_PREFIX)
app.include_router(clients.router, prefix=API_PREFIX)
app.include_router(circuits.router, prefix=API_PREFIX)
app.include_router(drivers.router, prefix=API_PREFIX)
app.include_router(teams.router, prefix=API_PREFIX)
app.include_router(shootings.router, prefix=API_PREFIX)
app.include_router(engagements.router, prefix=API_PREFIX)
app.include_router(batches.router, prefix=API_PREFIX)
app.include_router(media.router, prefix=API_PREFIX)
app.include_router(cameras.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(jobs.router, prefix=API_PREFIX)

# Routeurs J2
app.include_router(search.router, prefix=API_PREFIX)
app.include_router(review.router, prefix=API_PREFIX)
app.include_router(settings_router.router, prefix=API_PREFIX)
app.include_router(collections.router, prefix=API_PREFIX)
app.include_router(stats.router, prefix=API_PREFIX)

# Routeurs J3
app.include_router(billing.router, prefix=API_PREFIX)
app.include_router(sharing.router, prefix=API_PREFIX)
app.include_router(dashboard.router, prefix=API_PREFIX)
app.include_router(cron.router, prefix=API_PREFIX)
# `public` est un routeur dédié, cloisonné, sans identifiant de ressource en paramètre
# (§3-L.3) — préfixe propre, pas de PREFIX interne partagé avec le reste de l'API.
app.include_router(public.router, prefix=f"{API_PREFIX}/public")


@app.on_event("startup")
def _bootstrap_demo_users() -> None:
    """Garantit l'existence des 2 comptes de démo (§3-I) — idempotent, base réelle.

    **N'empêche jamais le démarrage.** Cette fonction levait, et l'application entière
    refusait alors de se lancer : une indisponibilité passagère de la base — le pooler
    Supabase à court de connexions, constaté en production — rendait l'API totalement
    morte, `GET /health` compris. Or `/health` est précisément l'endpoint censé dire *ce
    qui* ne va pas ; le voir tomber avec le reste supprime le seul moyen de diagnostiquer.

    L'échec est donc consigné et le démarrage se poursuit : les routes qui n'ont pas besoin
    de la base répondent, `/health` annonce `db: down`, et la tentative suivante recréera
    les comptes — l'opération est idempotente.
    """
    db = None
    try:
        # `SessionLocal()` est dans le `try` : la création de session peut échouer elle
        # aussi (pool épuisé, moteur mal configuré), et un hook de démarrage qui prétend
        # ne jamais lever doit couvrir tout ce qu'il fait, pas seulement sa partie facile.
        db = SessionLocal()
        ensure_demo_users(db)
        db.commit()
    except Exception:
        if db is not None:
            db.rollback()
        logging.getLogger(__name__).warning(
            "Comptes de démonstration non initialisés au démarrage — "
            "la base est injoignable, nouvelle tentative au prochain démarrage.",
            exc_info=True,
        )
    finally:
        if db is not None:
            db.close()


@app.get("/api/v1/health", tags=["health"], summary="Vérification de disponibilité")
def health() -> dict[str, str]:
    """Public — pas d'authentification requise. Vérifie la base **et** le stockage.

    Le champ `storage` a longtemps valu `"unknown"` en dur : un contrôle de santé qui
    ignore la moitié de ce dont l'application dépend ne dit pas grand-chose. Il teste
    désormais une vraie lecture de métadonnées sur le stockage objet — assez pour
    distinguer « clés invalides » ou « bucket disparu » d'un incident de base.

    Volontairement une lecture, jamais une écriture : un contrôle de santé sollicité en
    boucle ne doit pas laisser de traces, ni consommer de quota.
    """
    db_status = "ok"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "down"

    storage_status = "ok"
    try:
        # `object_size` sur une clé qui n'existe pas : la réponse importe peu, ce qui
        # compte est que l'appel aboutisse sans erreur d'authentification ni de réseau.
        get_storage_client().object_size("healthcheck/probe")
    except Exception:
        storage_status = "down"

    healthy = db_status == "ok" and storage_status == "ok"
    return {
        "status": "ok" if healthy else "degraded",
        "db": db_status,
        "storage": storage_status,
    }
