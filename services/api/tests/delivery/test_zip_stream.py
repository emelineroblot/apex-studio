"""L'archive est construite **en flux** (§3-M, Option 2) — la propriété à protéger.

Le critère d'acceptation dit « construite en flux, sans charger la collection en mémoire ».
C'est une propriété qu'aucune relecture de code ne garantit durablement : il suffit d'un
`b"".join(...)` ajouté un jour pour la perdre, sans qu'aucun autre test ne bronche. On la
mesure donc, avec `tracemalloc` — qui compte les allocations Python, exactement là où une
régression de ce type se produirait.

Le second test vérifie que le résultat est une archive ZIP valide au sens de la
bibliothèque standard, et pas seulement une suite d'octets que notre propre code sait
relire.
"""

from __future__ import annotations

import io
import tracemalloc
import zipfile
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from apex.models.billing import ClientSelection, SelectionItem
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

#: Assez d'entrées et de volume pour qu'une mise en mémoire complète soit visible, assez
#: peu pour que le test reste rapide.
ENTRY_COUNT = 40
ENTRY_BYTES = 512 * 1024
TOTAL_BYTES = ENTRY_COUNT * ENTRY_BYTES

#: Le tampon de `LocalDiskStorage` est de 64 Ko ; la marge couvre les structures de
#: `zipstream` et le bruit de l'interpréteur, tout en restant très loin des 20 Mo que
#: coûterait une archive assemblée en mémoire.
MEMORY_CEILING_BYTES = 4 * 1024 * 1024


@pytest.fixture
def large_selection(db_session: Session) -> int:
    owner = make_user(db_session, role="owner", email="owner-zip@apex-test.dev")
    circuit = make_circuit(db_session, "Circuit ZIP")
    demo_client = make_client(db_session, "Client ZIP")
    camera = make_camera(db_session)
    base = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
    shooting = make_shooting(db_session, client=demo_client, circuit=circuit, starts_at=base)
    batch = make_upload_batch(db_session, user=owner)
    storage = get_storage_client()

    from apex.models.collection import Collection

    collection = Collection(
        client_id=demo_client.id, title="Grosse livraison", status="published", created_by=owner.id
    )
    db_session.add(collection)
    db_session.flush()
    selection = ClientSelection(collection_id=collection.id, status="validated")
    db_session.add(selection)
    db_session.flush()

    # Tronqué à la taille exacte : un octet de plus ou de moins rendrait l'assertion de
    # taille du test suivant illisible. Les deux premiers octets sont ceux d'un JPEG, pour
    # que le contenu ressemble à ce qu'il prétend être.
    payload = (bytes([0xFF, 0xD8]) + b"apex" * (ENTRY_BYTES // 4 + 1))[:ENTRY_BYTES]
    for index in range(ENTRY_COUNT):
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
        key = f"hd/zip-{media.id}.jpg"
        storage.put_bytes(key, payload)
        media.storage_key_hd = key
        db_session.add(SelectionItem(selection_id=selection.id, media_id=media.id))
    db_session.commit()
    return selection.id


def test_larchive_ne_charge_jamais_la_collection_en_memoire(db_session, large_selection) -> None:
    storage = get_storage_client()
    stream = delivery_service.build_zip_stream(db_session, storage, large_selection)

    # La taille est connue **avant** d'avoir produit un octet : c'est ce que permet
    # `ZIP_STORED`, et c'est ce qui donne un `Content-Length` exact au navigateur.
    announced = len(stream)
    assert announced > TOTAL_BYTES

    tracemalloc.start()
    written = 0
    try:
        for chunk in stream:
            written += len(chunk)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert written == announced, "la taille annoncée doit être la taille réellement produite"
    assert peak < MEMORY_CEILING_BYTES, (
        f"pic mémoire {peak / 1024 / 1024:.1f} Mo pour une archive de "
        f"{written / 1024 / 1024:.1f} Mo — l'archive est assemblée en mémoire"
    )


def test_larchive_produite_est_lisible_par_la_bibliotheque_standard(
    db_session, large_selection
) -> None:
    storage = get_storage_client()
    stream = delivery_service.build_zip_stream(db_session, storage, large_selection)
    buffer = io.BytesIO(b"".join(stream))

    with zipfile.ZipFile(buffer) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert len(names) == ENTRY_COUNT
        assert names == sorted(names)
        assert len(archive.read(names[0])) == ENTRY_BYTES
        # `ZIP_STORED` : les JPEG sont déjà compressés, les recompresser coûterait du CPU
        # pour rien — et interdirait de calculer la taille à l'avance.
        assert all(info.compress_type == zipfile.ZIP_STORED for info in archive.infolist())


def test_un_nom_dentree_reste_trie_et_sans_collision(db_session, large_selection) -> None:
    media_list = delivery_service.selected_media(db_session, large_selection)
    names = [
        delivery_service.entry_name(position, media, [])
        for position, media in enumerate(media_list, start=1)
    ]
    assert len(set(names)) == len(names)
    assert names == sorted(names), "le rang en tête doit survivre à un tri alphabétique"


def test_le_nom_darchive_est_toujours_utilisable(db_session) -> None:
    """Un `Content-Disposition` mal formé casse le téléchargement chez certains
    navigateurs plutôt que de dégrader le nom."""
    name = delivery_service.archive_filename("Écurie Rouge / Sport", "Sélection « GP 2026 »")
    assert name.endswith(".zip")
    assert name.isascii()
    assert not any(c in name for c in ' /\\"')
