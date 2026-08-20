"""File de validation OCR — traitement en lot, navigation clavier côté frontend (J2, §3-J.4)."""

from fastapi import APIRouter, Query, Security

from apex.routers._common import bearer_scheme, not_implemented
from apex.schemas.review import ReviewDecisionsRequest, ReviewDecisionsResponse, ReviewQueueResponse

router = APIRouter(prefix="/review", tags=["review"], dependencies=[Security(bearer_scheme)])


@router.get("/queue", response_model=ReviewQueueResponse, summary="File de validation")
def review_queue(
    shooting_id: int | None = None,
    cursor: str | None = None,
    limit: int = Query(default=25, le=100),
) -> ReviewQueueResponse:
    not_implemented("GET /review/queue")


@router.post(
    "/decisions",
    response_model=ReviewDecisionsResponse,
    summary="Appliquer des décisions en lot (transaction unique)",
)
def review_decisions(payload: ReviewDecisionsRequest) -> ReviewDecisionsResponse:
    not_implemented("POST /review/decisions")
