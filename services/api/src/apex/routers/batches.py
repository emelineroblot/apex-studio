"""Upload par lot — `upload_batch` (§3-F.4). Enqueue transactionnel : impossible d'avoir
un média en base sans job associé.
"""

from fastapi import APIRouter, File, Header, Security, UploadFile

from apex.routers._common import bearer_scheme, not_implemented
from apex.schemas.batch import (
    BatchCloseResponse,
    BatchCreateRequest,
    BatchCreateResponse,
    BatchStatusResponse,
    FileUploadResponse,
)

router = APIRouter(prefix="/batches", tags=["batches"], dependencies=[Security(bearer_scheme)])


@router.post("", response_model=BatchCreateResponse, status_code=201, summary="Ouvrir un lot")
def create_batch(payload: BatchCreateRequest) -> BatchCreateResponse:
    not_implemented("POST /batches")


@router.post(
    "/{batch_id}/files",
    response_model=FileUploadResponse,
    status_code=201,
    summary="Déposer un fichier dans le lot (upload idempotent)",
)
def upload_file(
    batch_id: int,
    file: UploadFile = File(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> FileUploadResponse:
    not_implemented("POST /batches/{id}/files")


@router.post("/{batch_id}/close", response_model=BatchCloseResponse, summary="Clôturer un lot")
def close_batch(batch_id: int) -> BatchCloseResponse:
    not_implemented("POST /batches/{id}/close")


@router.get(
    "/{batch_id}",
    response_model=BatchStatusResponse,
    summary="Suivi du lot (polling 1 s) — déclenche un tick si la file n'est pas vide",
)
def get_batch(batch_id: int) -> BatchStatusResponse:
    not_implemented("GET /batches/{id}")
