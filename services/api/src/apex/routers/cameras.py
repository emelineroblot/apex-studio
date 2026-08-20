"""`GET /cameras`, `PATCH /cameras/{id}` — décalage d'horloge, corrige rétroactivement le
rattachement (§3-F.3) via l'enqueue de `reattach_camera`.
"""

from fastapi import APIRouter, Security

from apex.routers._common import bearer_scheme, not_implemented
from apex.schemas.catalog import CameraOut, CameraPatch, CameraPatchResponse

router = APIRouter(prefix="/cameras", tags=["cameras"], dependencies=[Security(bearer_scheme)])


@router.get("", response_model=list[CameraOut], summary="Liste des boîtiers")
def list_cameras() -> list[CameraOut]:
    not_implemented("GET /cameras")


@router.patch(
    "/{camera_id}",
    response_model=CameraPatchResponse,
    summary="Régler le décalage d'horloge / la propriété d'un boîtier",
)
def patch_camera(camera_id: int, payload: CameraPatch) -> CameraPatchResponse:
    not_implemented("PATCH /cameras/{id}")
