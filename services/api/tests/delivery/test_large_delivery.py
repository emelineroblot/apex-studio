"""Bascule « grosse collection » : au-delà de `zip_stream_max_items`, l'archive est
construite **une fois** par le worker et déposée sur le stockage objet (§3-M).

Cette branche ne s'exécute jamais dans les autres tests — le seuil vaut 200 et personne ne
fabrique deux cents médias pour vérifier un `if`. On abaisse donc le seuil par le réglage
prévu pour ça, ce qui a l'avantage de vérifier au passage que ce réglage est réellement lu.

Ce qui est en jeu n'est pas cosmétique : le flux direct n'a pas de reprise par plage. Passé
un certain volume, une coupure réseau oblige à tout recommencer, d'où l'archive stockée.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from apex.db import SessionLocal
from apex.models.billing import ClientSelection, Delivery, SelectionItem
from apex.models.collection import Collection
from apex.models.setting import AppSetting
from apex.queue.enqueue import enqueue
from apex.queue.runner import drain
from apex.services import delivery as delivery_service
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

SMALL_THRESHOLD = 2
MEDIA_COUNT = 4


def _build_selection(db_session: Session, *, suffix: str, count: int) -> int:
    """Crée une sélection validée de `count` médias, chacun avec un vrai fichier HD, et
    enfile son `build_delivery`. Renvoie l'identifiant de la livraison."""
    owner = make_user(db_session, role="owner", email=f"owner-{suffix}@apex-test.dev")
    circuit = make_circuit(db_session, f"Circuit {suffix}")
    demo_client = make_client(db_session, f"Client {suffix}")
    camera = make_camera(db_session)
    base = datetime(2026, 6, 20, 9, 0, tzinfo=UTC)
    shooting = make_shooting(db_session, client=demo_client, circuit=circuit, starts_at=base)
    batch = make_upload_batch(db_session, user=owner)
    storage = get_storage_client()

    collection = Collection(
        client_id=demo_client.id,
        title=f"Collection {suffix}",
        status="published",
        created_by=owner.id,
    )
    db_session.add(collection)
    db_session.flush()
    selection = ClientSelection(collection_id=collection.id, status="validated")
    db_session.add(selection)
    db_session.flush()

    for index in range(count):
        media = make_media(
            db_session,
            batch=batch,
            user=owner,
            shooting=shooting,
            camera=camera,
            shot_at=base + timedelta(seconds=index),
            attachment_status="shooting_attached",
            attachment_source="pipeline_time",
        )
        key = f"hd/{suffix}-{media.id}.jpg"
        storage.put_bytes(key, bytes([0xFF, 0xD8]) + b"x" * 4096)
        media.storage_key_hd = key
        db_session.add(SelectionItem(selection_id=selection.id, media_id=media.id))

    delivery = Delivery(collection_id=collection.id, selection_id=selection.id, status="pending")
    db_session.add(delivery)
    db_session.flush()
    enqueue(
        db_session,
        "build_delivery",
        {"delivery_id": delivery.id},
        dedupe_key=f"delivery:{delivery.id}",
    )
    db_session.commit()
    return delivery.id


@pytest.fixture
def oversized_selection(db_session: Session) -> int:
    """Une sélection au-dessus du seuil — abaissé par réglage pour rester rapide."""
    db_session.add(AppSetting(key=delivery_service.ZIP_STREAM_MAX_ITEMS_KEY, value=SMALL_THRESHOLD))
    return _build_selection(db_session, suffix="large", count=MEDIA_COUNT)


@pytest.fixture
def undersized_selection(db_session: Session) -> int:
    """Même chose, mais sous le seuil par défaut (200) : aucun réglage n'est posé."""
    return _build_selection(db_session, suffix="small", count=2)


def test_le_reglage_de_seuil_est_bien_lu(db_session, oversized_selection) -> None:
    """Sans cette lecture, la bascule serait un seuil codé en dur — et le test suivant
    prouverait seulement que 4 > 200 est faux."""
    assert delivery_service.get_zip_stream_max_items(db_session) == SMALL_THRESHOLD


def test_au_dela_du_seuil_larchive_est_deposee_sur_le_stockage(
    db_session, oversized_selection
) -> None:
    result = drain(SessionLocal, "test-large-delivery", deadline=None, excluded_kinds=())
    assert not result.errors, result.errors

    delivery = db_session.get(Delivery, oversized_selection)
    db_session.refresh(delivery)
    assert delivery.status == "ready"
    assert delivery.item_count == MEDIA_COUNT
    assert delivery.storage_key is not None, "au-delà du seuil, l'archive doit être stockée"

    stored = get_storage_client().open_stream(delivery.storage_key)
    body = b"".join(stored.chunks)
    # L'archive déposée est complète et relisible : c'est elle que le client téléchargera,
    # le flux direct n'étant plus emprunté pour cette livraison.
    assert body[:2] == b"PK"
    assert len(body) == delivery.byte_size


def test_sous_le_seuil_rien_nest_stocke(db_session, undersized_selection) -> None:
    """Contre-épreuve : le chemin nominal ne doit rien écrire. Sans elle, un code qui
    stockerait *toujours* l'archive passerait le test précédent."""
    result = drain(SessionLocal, "test-small-delivery", deadline=None, excluded_kinds=())
    assert not result.errors, result.errors

    delivery = db_session.get(Delivery, undersized_selection)
    db_session.refresh(delivery)
    assert delivery.status == "ready"
    assert delivery.storage_key is None, "sous le seuil, l'archive est produite à la volée"
