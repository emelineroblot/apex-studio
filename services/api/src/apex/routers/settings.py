"""`/settings/ocr` — **Directives** du principe DOE (§3-J.2) : seuils éditables, jamais en dur.

Deux nombres, éditables par le dirigeant depuis l'UI, qui redistribuent instantanément
plusieurs milliers de médias entre rattachement automatique, file de validation et
abstention — **sans jamais relancer une seule inférence**. C'est la conséquence directe du
choix de persister les candidats bruts (§3-J.4) :

- `PUT` **simule** d'abord (`preview_distribution`, agrégat SQL sur `media_ocr_candidate`,
  aucune écriture), puis écrit les seuils et enqueue `reclassify_ocr` dans la **même**
  transaction (§3-E.4.2) — jamais de seuil écrit sans re-projection.
- Un court tick de drainage suit le commit, pour que la redistribution soit visible dès la
  réponse en environnement serverless (§3-E.7, même motif que `GET /batches/{id}`).

Écriture réservée au rôle `owner` (contrat J2).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Security
from sqlalchemy.orm import Session

from apex.db import SessionLocal, get_db
from apex.pipeline.ocr import classify
from apex.queue.enqueue import enqueue, enqueue_unique_pending
from apex.queue.runner import drain
from apex.routers._common import bearer_scheme
from apex.schemas.settings import (
    OcrDistribution,
    OcrPreviewDistribution,
    OcrSettingsOut,
    OcrSettingsUpdate,
    OcrSettingsUpdateResponse,
)
from apex.security import CurrentUser
from apex.services import access
from apex.services.ocr_settings import (
    MAX_BOX_AREA_RATIO_KEY,
    MIN_BOX_AREA_RATIO_KEY,
    OCR_HIGH_KEY,
    OCR_LOW_KEY,
    OcrSettings,
    load_ocr_settings,
    write_ocr_settings,
)

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Security(bearer_scheme)])

#: Budget du tick déclenché après un changement de seuils — court, pour ne pas bloquer la
#: réponse HTTP. Le reste du travail, s'il en reste, est drainé par le polling suivant.
RECLASSIFY_DRAIN_BUDGET = timedelta(seconds=5)


def _to_out(ocr_settings: OcrSettings, distribution: classify.Distribution) -> OcrSettingsOut:
    return OcrSettingsOut(
        high=ocr_settings.high,
        low=ocr_settings.low,
        min_box_area_ratio=ocr_settings.min_box_area_ratio,
        max_box_area_ratio=ocr_settings.max_box_area_ratio,
        engine_version=ocr_settings.engine_version,
        updated_at=ocr_settings.updated_at,
        distribution=OcrDistribution(
            auto=distribution.auto,
            review=distribution.review,
            abstain=distribution.abstain,
            not_engaged=distribution.not_engaged,
        ),
    )


def _validate(payload: OcrSettingsUpdate) -> None:
    """Deux seuils, un ordre. Un `low > high` créerait une bande de validation vide et un
    comportement inexplicable : refusé au contrat plutôt que « corrigé » silencieusement.
    """
    errors: list[str] = []
    if not 0.0 <= payload.low <= 1.0:
        errors.append("« low » doit être compris entre 0 et 1.")
    if not 0.0 <= payload.high <= 1.0:
        errors.append("« high » doit être compris entre 0 et 1.")
    if payload.low > payload.high:
        errors.append("Le seuil bas ne peut pas dépasser le seuil haut.")
    for name, value in (
        ("min_box_area_ratio", payload.min_box_area_ratio),
        ("max_box_area_ratio", payload.max_box_area_ratio),
    ):
        if value is not None and not 0.0 < value <= 1.0:
            errors.append(f"« {name} » doit être compris entre 0 (exclu) et 1.")
    if (
        payload.min_box_area_ratio is not None
        and payload.max_box_area_ratio is not None
        and payload.min_box_area_ratio >= payload.max_box_area_ratio
    ):
        errors.append("« min_box_area_ratio » doit être strictement inférieur au maximum.")
    if errors:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_ocr_settings",
                "message": "Réglages OCR invalides.",
                "detail": {"errors": errors},
            },
        )


@router.get("/ocr", response_model=OcrSettingsOut, summary="Seuils OCR courants")
def get_ocr_settings(user: CurrentUser, db: Session = Depends(get_db)) -> OcrSettingsOut:
    ocr_settings = load_ocr_settings(db)
    return _to_out(ocr_settings, classify.current_distribution(db))


@router.put(
    "/ocr",
    response_model=OcrSettingsUpdateResponse,
    summary="Modifier les seuils OCR — `owner` uniquement, simule la redistribution",
)
def put_ocr_settings(
    payload: OcrSettingsUpdate, user: CurrentUser, db: Session = Depends(get_db)
) -> OcrSettingsUpdateResponse:
    access.require_owner(user, message="Seul le dirigeant peut modifier les seuils OCR.")
    _validate(payload)

    # 1. Simulation — pure lecture, avant toute écriture (contrat J2 : « simulation avant
    #    application »). Ce sont ces chiffres que l'UI affiche pour justifier le changement.
    preview = classify.simulate_distribution(db, high=payload.high, low=payload.low)

    # 2. Écriture des Directives + enqueue de la re-projection, dans la même transaction.
    values: dict[str, float] = {OCR_HIGH_KEY: payload.high, OCR_LOW_KEY: payload.low}
    if payload.min_box_area_ratio is not None:
        values[MIN_BOX_AREA_RATIO_KEY] = payload.min_box_area_ratio
    if payload.max_box_area_ratio is not None:
        values[MAX_BOX_AREA_RATIO_KEY] = payload.max_box_area_ratio
    write_ocr_settings(db, values, updated_by=user.id)

    job_id = enqueue(db, "reclassify_ocr", {}, dedupe_key="reclassify", priority=80)
    if job_id is None:
        # Une re-projection est déjà en file : elle lira les seuils **à son exécution**,
        # donc ceux qu'on vient d'écrire. On renvoie son id plutôt que d'en empiler un
        # second (§3-E.4.2, dédoublonnage d'enqueue).
        job_id = enqueue_unique_pending(db, "reclassify_ocr", "reclassify")
    if job_id is None:
        # Course improbable (le job vivant s'est terminé entre les deux requêtes) : on
        # insère sans clé de dédoublonnage plutôt que de renvoyer un identifiant fictif.
        # Un seuil ne doit jamais être écrit sans re-projection qui le suive.
        job_id = enqueue(db, "reclassify_ocr", {}, priority=80)
    assert job_id is not None  # un enqueue sans dedupe_key insère toujours
    db.commit()

    # 3. Tick court : la redistribution doit être perceptible immédiatement en démo.
    db.rollback()  # relâche la connexion avant que `drain()` en réclame une (cf. batches.py)
    drain(
        SessionLocal,
        f"http-settings-{uuid4().hex[:12]}",
        deadline=datetime.now(UTC) + RECLASSIFY_DRAIN_BUDGET,
        batch_size=4,
    )
    db.expire_all()

    ocr_settings = load_ocr_settings(db)
    return OcrSettingsUpdateResponse(
        settings=_to_out(ocr_settings, classify.current_distribution(db)),
        reclassify_job_id=job_id,
        preview_distribution=OcrPreviewDistribution(
            auto=preview.auto, review=preview.review, abstain=preview.abstain
        ),
    )
