"""Espace client — routeur **dédié** et cloisonné (§3-L.3, J3).

Une seule dépendance d'authentification prévue au Lot J3 : `client_scope` (JWT de session
client, `scope='client'`, échangé contre le jeton long via `POST /public/session`).
`bearer_scheme` ci-dessous n'est qu'un repère OpenAPI pour le lot 0 — la vérification
réelle (portée à la collection du jeton, jamais un identifiant en paramètre) arrive avec
le reste du jalon J3. Toute ressource hors périmètre doit répondre `404`, jamais `403`.
"""

from fastapi import APIRouter, Security
from fastapi.responses import StreamingResponse

from apex.routers._common import bearer_scheme, not_implemented
from apex.schemas.public import (
    PublicCollectionResponse,
    PublicDeliveryStatusResponse,
    PublicSelectionItemResponse,
    PublicSelectionItemUpdate,
    PublicSelectionResponse,
    PublicSelectionValidateResponse,
    PublicSessionRequest,
    PublicSessionResponse,
)

router = APIRouter(tags=["public"])


@router.post(
    "/session",
    response_model=PublicSessionResponse,
    summary="Échange du jeton long contre une session courte (30 min)",
    responses={410: {"description": 'Lien expiré ou révoqué — `{"code": "link_expired"}`'}},
)
def public_session(payload: PublicSessionRequest) -> PublicSessionResponse:
    not_implemented("POST /public/session")


@router.get(
    "/collection",
    response_model=PublicCollectionResponse,
    summary="Aperçus filigranés de la collection du jeton",
    dependencies=[Security(bearer_scheme)],
)
def public_collection(
    cursor: str | None = None, limit: int = 50, selected_only: bool = False
) -> PublicCollectionResponse:
    not_implemented("GET /public/collection")


@router.get(
    "/media/{media_id}/file/preview",
    summary="Flux filigrané — `404` si le média est hors de la collection du jeton",
    dependencies=[Security(bearer_scheme)],
)
def public_media_preview(media_id: int) -> StreamingResponse:
    not_implemented("GET /public/media/{media_id}/file/preview")


@router.put(
    "/selection/items/{media_id}",
    response_model=PublicSelectionItemResponse,
    summary="Sélectionner / commenter une photo — `409` si la sélection est déjà validée",
    dependencies=[Security(bearer_scheme)],
)
def put_selection_item(
    media_id: int, payload: PublicSelectionItemUpdate
) -> PublicSelectionItemResponse:
    not_implemented("PUT /public/selection/items/{media_id}")


@router.delete(
    "/selection/items/{media_id}",
    status_code=204,
    summary="Retirer une photo de la sélection",
    dependencies=[Security(bearer_scheme)],
)
def delete_selection_item(media_id: int) -> None:
    not_implemented("DELETE /public/selection/items/{media_id}")


@router.get(
    "/selection",
    response_model=PublicSelectionResponse,
    summary="Sélection courante",
    dependencies=[Security(bearer_scheme)],
)
def get_public_selection() -> PublicSelectionResponse:
    not_implemented("GET /public/selection")


@router.post(
    "/selection/validate",
    response_model=PublicSelectionValidateResponse,
    summary="Valider la sélection — déclenche `build_delivery` et `refresh_draft_invoice`",
    dependencies=[Security(bearer_scheme)],
)
def validate_selection() -> PublicSelectionValidateResponse:
    not_implemented("POST /public/selection/validate")


@router.get(
    "/delivery",
    response_model=PublicDeliveryStatusResponse,
    summary="État de la préparation de livraison",
    dependencies=[Security(bearer_scheme)],
)
def get_public_delivery() -> PublicDeliveryStatusResponse:
    not_implemented("GET /public/delivery")


@router.get(
    "/delivery/archive",
    summary="Flux ZIP — `403` si sélection non validée ou livraison non prête",
    dependencies=[Security(bearer_scheme)],
)
def get_public_delivery_archive() -> StreamingResponse:
    not_implemented("GET /public/delivery/archive")
