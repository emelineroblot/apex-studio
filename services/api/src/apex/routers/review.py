"""File de validation OCR — traitement en lot, navigation clavier côté frontend (§3-J.4).

C'est ici que se joue « l'IA propose, l'humain arbitre » (`AGENTS.md`). Trois principes :

- **Rien n'est rattaché de force.** La file ne contient que les candidats de la bande
  intermédiaire (`resolution='review'`) ; au-dessus le rattachement est automatique, en
  dessous on s'abstient, et un numéro absent des engagements part dans le bac
  « incohérences » — jamais dans la file, parce qu'accepter n'y voudrait rien dire.
- **Une décision humaine est terminale.** `accepted` / `rejected` ne sont jamais réécrits :
  ni par une re-projection, ni par un changement de seuil, ni par un rejeu de `ocr_media`.
- **Qui a tranché est tracé.** `resolved_by` / `resolved_at` sur le candidat, et
  `media_engagement.created_by` sur le rattachement qui en découle — c'est cette colonne
  qui distingue ensuite `auto_ocr` de `human` dans le taux de rattachement automatique.

Les décisions arrivent **en lot** (l'écran se traite au clavier, `Espace` pour marquer,
`Entrée` pour appliquer) : une seule transaction, et les erreurs sont rapportées ligne par
ligne plutôt que de faire échouer tout le lot.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from apex.db import get_db
from apex.models.catalog import Client, Driver, Team
from apex.models.media import Media
from apex.models.search import MediaOcrCandidate
from apex.models.shooting import Engagement
from apex.pipeline.ocr import classify
from apex.routers._common import bearer_scheme
from apex.schemas.review import (
    OcrBoundingBox,
    ReviewDecision,
    ReviewDecisionError,
    ReviewDecisionsRequest,
    ReviewDecisionsResponse,
    ReviewItem,
    ReviewMediaRef,
    ReviewQueueResponse,
    SuggestedEngagement,
)
from apex.security import CurrentUser
from apex.services import access
from apex.services.ocr_settings import load_ocr_settings
from apex.services.pagination import paginate_by_id
from apex.services.search_projection import project_media_search

router = APIRouter(prefix="/review", tags=["review"], dependencies=[Security(bearer_scheme)])

#: Nombre d'engagements alternatifs proposés — calé sur les raccourcis clavier `1`-`9`.
MAX_ALTERNATIVES = 9


def _queue_stmt(user, shooting_id: int | None) -> Select:
    """Candidats en attente d'arbitrage, cloisonnés au périmètre de l'utilisateur."""
    stmt = (
        select(MediaOcrCandidate)
        .join(Media, Media.id == MediaOcrCandidate.media_id)
        .where(MediaOcrCandidate.resolution == classify.RESOLUTION_REVIEW)
    )
    visibility = access.media_visibility_clause(user)
    if visibility is not None:
        stmt = stmt.where(visibility)
    if shooting_id is not None:
        stmt = stmt.where(Media.shooting_id == shooting_id)
    return stmt


def _engagement_labels(
    session: Session, engagement_ids: set[int], shooting_ids: set[int]
) -> dict[int, SuggestedEngagement]:
    """Résout numéro → pilote → écurie → client en une requête. **La jointure métier.**

    C'est elle qui donne son sens au numéro lu : sans la table des engagements du shooting,
    « 12 » n'est qu'un dessin sur une portière.
    """
    if not engagement_ids and not shooting_ids:
        return {}
    stmt = (
        select(
            Engagement.id,
            Engagement.car_number,
            Driver.full_name,
            Team.name,
            Client.name,
        )
        .select_from(Engagement)
        .outerjoin(Driver, Driver.id == Engagement.driver_id)
        .outerjoin(Team, Team.id == Engagement.team_id)
        .outerjoin(Client, Client.id == Engagement.client_id)
    )
    conditions = []
    if engagement_ids:
        conditions.append(Engagement.id.in_(engagement_ids))
    if shooting_ids:
        conditions.append(Engagement.shooting_id.in_(shooting_ids))
    stmt = stmt.where(conditions[0] if len(conditions) == 1 else or_(*conditions))

    return {
        row[0]: SuggestedEngagement(
            id=row[0], car_number=row[1], driver=row[2], team=row[3], client=row[4]
        )
        for row in session.execute(stmt).all()
    }


def _engagements_by_shooting(session: Session, shooting_ids: set[int]) -> dict[int, list[int]]:
    if not shooting_ids:
        return {}
    rows = session.execute(
        select(Engagement.shooting_id, Engagement.id)
        .where(Engagement.shooting_id.in_(shooting_ids))
        .order_by(Engagement.shooting_id, Engagement.car_number)
    ).all()
    grouped: dict[int, list[int]] = {}
    for shooting_id, engagement_id in rows:
        grouped.setdefault(shooting_id, []).append(engagement_id)
    return grouped


@router.get("/queue", response_model=ReviewQueueResponse, summary="File de validation")
def review_queue(
    user: CurrentUser,
    shooting_id: int | None = None,
    cursor: str | None = None,
    limit: int = Query(default=25, le=100),
    db: Session = Depends(get_db),
) -> ReviewQueueResponse:
    stmt = _queue_stmt(user, shooting_id)
    candidates, next_cursor, _total = paginate_by_id(
        db, stmt, MediaOcrCandidate.id, cursor=cursor, limit=limit
    )

    remaining = int(
        db.execute(
            select(func.count()).select_from(_queue_stmt(user, shooting_id).subquery())
        ).scalar_one()
    )

    media_ids = {candidate.media_id for candidate in candidates}
    medias = {
        media.id: media
        for media in db.execute(select(Media).where(Media.id.in_(media_ids))).scalars()
    }
    shooting_ids = {m.shooting_id for m in medias.values() if m.shooting_id is not None}
    labels = _engagement_labels(
        db,
        {c.engagement_id for c in candidates if c.engagement_id is not None},
        shooting_ids,
    )
    by_shooting = _engagements_by_shooting(db, shooting_ids)

    items: list[ReviewItem] = []
    for candidate in candidates:
        media = medias.get(candidate.media_id)
        if media is None:
            continue
        suggested = (
            labels.get(candidate.engagement_id) if candidate.engagement_id is not None else None
        )
        alternatives = [
            labels[engagement_id]
            for engagement_id in by_shooting.get(media.shooting_id or -1, [])
            if engagement_id != candidate.engagement_id and engagement_id in labels
        ][:MAX_ALTERNATIVES]
        items.append(
            ReviewItem(
                candidate_id=candidate.id,
                media=ReviewMediaRef(
                    id=media.id,
                    thumb_url=f"/media/{media.id}/file/thumb",
                    preview_url=f"/media/{media.id}/file/preview",
                    shot_at=media.shot_at.isoformat() if media.shot_at else None,
                ),
                raw_text=candidate.raw_text,
                normalized_number=candidate.normalized_number,
                confidence=float(candidate.confidence),
                bbox=OcrBoundingBox.model_validate(candidate.bbox),
                resolution=candidate.resolution,
                suggested_engagement=suggested,
                other_engagements=alternatives,
            )
        )

    return ReviewQueueResponse(items=items, remaining=remaining, next_cursor=next_cursor)


def _apply_decision(
    db: Session,
    user,
    decision: ReviewDecision,
    now: datetime,
) -> tuple[int | None, str | None]:
    """Applique une décision. Renvoie `(media_id touché, message d'erreur)`.

    Une erreur n'annule pas le lot : elle est rapportée pour cette ligne seulement.
    """
    candidate = db.get(MediaOcrCandidate, decision.candidate_id)
    if candidate is None:
        return None, "Candidat introuvable."

    media = db.get(Media, candidate.media_id)
    if media is None:
        return None, "Média introuvable."
    try:
        access.assert_can_read_media(db, user, media)
    except HTTPException:
        # Convention du projet : hors périmètre ⇒ « introuvable », jamais « interdit » —
        # un message distinct révélerait l'existence de la ressource (§3-I).
        return None, "Candidat introuvable."

    if candidate.resolution in classify.HUMAN_RESOLUTIONS:
        return None, "Ce candidat a déjà été arbitré."
    if candidate.resolution != classify.RESOLUTION_REVIEW:
        return None, (
            "Ce candidat n'est pas dans la file de validation "
            f"(résolution actuelle : « {candidate.resolution} »)."
        )

    if decision.action == "reject":
        candidate.resolution = classify.RESOLUTION_REJECTED
        candidate.engagement_id = None
    elif decision.action == "accept":
        if candidate.engagement_id is None:
            return None, "Aucun engagement suggéré : utilisez « reassign »."
        candidate.resolution = classify.RESOLUTION_ACCEPTED
    elif decision.action == "reassign":
        if decision.engagement_id is None:
            return None, "« engagement_id » est requis pour un réaffectation."
        engagement = db.get(Engagement, decision.engagement_id)
        if engagement is None or engagement.shooting_id != media.shooting_id:
            # Un engagement d'un autre shooting n'a aucun sens ici : le numéro n'existe
            # que rapporté à **son** événement (invariant `AGENTS.md`).
            return None, "Engagement inconnu pour le shooting de ce média."
        candidate.resolution = classify.RESOLUTION_ACCEPTED
        candidate.engagement_id = engagement.id
    else:  # pragma: no cover — `ReviewAction` est un Literal fermé
        return None, f"Action inconnue : {decision.action}."

    candidate.resolved_by = user.id
    candidate.resolved_at = now
    return candidate.media_id, None


@router.post(
    "/decisions",
    response_model=ReviewDecisionsResponse,
    summary="Appliquer des décisions en lot (transaction unique)",
)
def review_decisions(
    payload: ReviewDecisionsRequest, user: CurrentUser, db: Session = Depends(get_db)
) -> ReviewDecisionsResponse:
    now = datetime.now(UTC)
    errors: list[ReviewDecisionError] = []
    touched: set[int] = set()

    for decision in payload.decisions:
        media_id, error = _apply_decision(db, user, decision, now)
        if error is not None:
            errors.append(ReviewDecisionError(candidate_id=decision.candidate_id, message=error))
            continue
        if media_id is not None:
            touched.add(media_id)

    db.flush()
    if touched:
        # Matérialise les rattachements décidés et recalcule `attachment_status`. Passe par
        # exactement le même code que la projection automatique : un rattachement humain et
        # un rattachement machine produisent la même forme en base, seule leur traçabilité
        # diffère.
        classify.project_media_batch(db, sorted(touched), load_ocr_settings(db))
        # L'arbitrage humain change `attachment_status` (accepté/rejeté/réaffecté) — la
        # projection de recherche doit suivre dans la même transaction (§3-K).
        project_media_search(db, sorted(touched))
    db.commit()

    remaining = int(
        db.execute(
            select(func.count()).select_from(_queue_stmt(user, None).subquery())
        ).scalar_one()
    )
    applied = len(payload.decisions) - len(errors)
    return ReviewDecisionsResponse(
        applied=applied, skipped=len(errors), errors=errors, remaining=remaining
    )
