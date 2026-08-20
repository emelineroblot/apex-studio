"""Application FastAPI — point d'entrée `apex.main:app`.

Sert aussi bien en local (`uvicorn apex.main:app`) qu'en serverless (`api/index.py`,
Vercel). CORS restreint à l'origine du frontend (Décision A : pas de cookie, JWT en
en-tête `Authorization`, donc pas de `credentials` à gérer).
"""

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
)
from apex.routers import settings as settings_router

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
    """Garantit l'existence des 2 comptes de démo (§3-I) — idempotent, base réelle."""
    db = SessionLocal()
    try:
        ensure_demo_users(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.get("/api/v1/health", tags=["health"], summary="Vérification de disponibilité")
def health() -> dict[str, str]:
    """Public — pas d'authentification requise. Vérifie la base et signale le stockage."""
    db_status = "ok"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "down"
    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "db": db_status,
        "storage": "unknown",
    }
