"""Fixtures de l'espace client — une collection réellement partageable.

Les médias portent de **vraies** variantes dans le stockage (vignette et aperçu WebP
écrits sur disque), pas seulement des lignes en base : les routes testées ici servent des
octets, filigranent une image et calculent des `ETag` à partir du contenu. Un média sans
fichier ne prouverait rien de tout cela.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta

import pytest
from PIL import Image
from sqlalchemy.orm import Session

from apex.models.billing import ShareLink
from apex.models.collection import Collection, CollectionItem
from apex.services import sharing
from apex.services.search_projection import project_media_search
from apex.services.storage import get_storage_client
from tests.conftest import make_user
from tests.search.factories import (
    make_camera,
    make_circuit,
    make_client,
    make_media,
    make_shooting,
    make_upload_batch,
)


def _webp_bytes(color: tuple[int, int, int], size: tuple[int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="WEBP", quality=80)
    return buffer.getvalue()


def _jpeg_bytes(color: tuple[int, int, int], size: tuple[int, int] = (800, 533)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


@pytest.fixture
def shared_collection(db_session: Session) -> dict:
    owner = make_user(db_session, role="owner", email="owner-public@apex-test.dev")
    photographer = make_user(
        db_session, role="photographer", email="photographer-public@apex-test.dev"
    )
    circuit = make_circuit(db_session, "Circuit Espace Client")
    demo_client = make_client(db_session, "Écurie Cliente")
    camera = make_camera(db_session)
    base = datetime(2026, 5, 12, 14, 0, tzinfo=UTC)
    shooting = make_shooting(db_session, client=demo_client, circuit=circuit, starts_at=base)
    batch = make_upload_batch(db_session, user=owner)
    storage = get_storage_client()

    media_ids: list[int] = []
    for index in range(3):
        media = make_media(
            db_session,
            batch=batch,
            user=owner,
            shooting=shooting,
            camera=camera,
            shot_at=base + timedelta(minutes=index),
            attachment_status="shooting_attached",
            attachment_source="pipeline_time",
        )
        thumb_key = f"thumb/test-public-{media.id}.webp"
        preview_key = f"preview/test-public-{media.id}.webp"
        hd_key = f"hd/test-public-{media.id}.jpg"
        storage.put_bytes(thumb_key, _webp_bytes((30, 60 + index * 20, 120), (320, 213)))
        storage.put_bytes(preview_key, _webp_bytes((30, 60 + index * 20, 120), (1600, 1067)))
        # Le HD est un vrai fichier : la livraison mesure sa taille avant de se declarer
        # prete, et l'archive le lit reellement.
        storage.put_bytes(hd_key, _jpeg_bytes((200, 40 + index * 30, 30)))
        media.storage_key_thumb = thumb_key
        media.storage_key_preview = preview_key
        media.storage_key_hd = hd_key
        media.content_hash = bytes([index]) * 32
        media_ids.append(media.id)

    # Un média hors collection, pour prouver que le cloisonnement ne dépend pas de
    # l'existence du média mais de son appartenance au périmètre du jeton.
    outsider = make_media(
        db_session,
        batch=batch,
        user=owner,
        shooting=shooting,
        camera=camera,
        shot_at=base + timedelta(hours=1),
        attachment_status="shooting_attached",
        attachment_source="pipeline_time",
    )

    collection = Collection(
        client_id=demo_client.id,
        shooting_id=shooting.id,
        title="Sélection Grand Prix",
        description="Les images à valider",
        status="published",
        created_by=owner.id,
    )
    db_session.add(collection)
    db_session.flush()
    for position, media_id in enumerate(media_ids):
        db_session.add(
            CollectionItem(collection_id=collection.id, media_id=media_id, position=position)
        )

    other_collection = Collection(
        client_id=demo_client.id,
        title="Collection d'un autre client",
        status="published",
        created_by=owner.id,
    )
    db_session.add(other_collection)
    db_session.flush()
    db_session.add(
        CollectionItem(collection_id=other_collection.id, media_id=outsider.id, position=0)
    )

    link, token = sharing.create_share_link(
        db_session, collection_id=collection.id, created_by=owner.id, expires_in_days=14
    )
    db_session.commit()
    project_media_search(db_session, None)
    db_session.commit()

    return {
        "owner": owner,
        "photographer": photographer,
        "client_id": demo_client.id,
        "collection": collection,
        "other_collection_id": other_collection.id,
        "media_ids": media_ids,
        "outsider_media_id": outsider.id,
        "link_id": link.id,
        "token": token,
    }


@pytest.fixture
def client_session(client, shared_collection) -> dict:
    """Session client ouverte — l'état de départ de presque tous les tests `/public`."""
    response = client.post("/api/v1/public/session", json={"token": shared_collection["token"]})
    assert response.status_code == 200, response.text
    body = response.json()
    return {
        "headers": {"Authorization": f"Bearer {body['access_token']}"},
        "body": body,
    }


def expire_link(db_session: Session, link_id) -> None:
    link = db_session.get(ShareLink, link_id)
    assert link is not None
    link.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
