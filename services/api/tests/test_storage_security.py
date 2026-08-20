"""Preuve du correctif revue J1 (🔴 n°4) : traversée de chemin via l'en-tête
`Idempotency-Key`. Deux niveaux, comme prescrit en revue :
- au routeur (`POST /batches/{id}/files`) → `422`, jamais d'écriture ;
- en défense en profondeur dans `LocalDiskStorage._path` → refuse toute clé qui
  échapperait à la racine, même si elle contournait la validation amont.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from apex.services.storage import LocalDiskStorage, PathTraversalError
from tests.conftest import auth_headers, make_user
from tests.support.images import make_valid_jpeg


class TestApiValidation:
    def test_path_traversal_idempotency_key_is_rejected(self, client, db_session) -> None:
        owner = make_user(db_session, role="owner", email="traversal-owner@apex-test.dev")
        headers = auth_headers(owner)
        batch = client.post("/api/v1/batches", json={"expected_count": 1}, headers=headers).json()

        resp = client.post(
            f"/api/v1/batches/{batch['id']}/files",
            headers={**headers, "Idempotency-Key": "../../../../etc/passwd"},
            files={"file": ("evil.jpg", make_valid_jpeg(), "image/jpeg")},
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "invalid_idempotency_key"

    def test_absolute_path_idempotency_key_is_rejected(self, client, db_session) -> None:
        owner = make_user(db_session, role="owner", email="traversal-owner-2@apex-test.dev")
        headers = auth_headers(owner)
        batch = client.post("/api/v1/batches", json={"expected_count": 1}, headers=headers).json()

        resp = client.post(
            f"/api/v1/batches/{batch['id']}/files",
            headers={**headers, "Idempotency-Key": "/etc/passwd"},
            files={"file": ("evil.jpg", make_valid_jpeg(), "image/jpeg")},
        )
        assert resp.status_code == 422


class TestStorageDefenseInDepth:
    """Même si la validation amont était contournée, `LocalDiskStorage` doit refuser
    d'écrire hors de sa racine — c'est la garantie de dernier recours (revue J1, 🔴 n°4).
    """

    def test_put_bytes_rejects_traversal_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "storage_root"
            storage = LocalDiskStorage(root)

            outside_marker = Path(tmp) / "escaped.txt"
            assert not outside_marker.exists()

            with pytest.raises(PathTraversalError):
                storage.put_bytes("../escaped.txt", b"contenu malveillant")

            # Aucun fichier écrit hors racine — la tentative a été refusée avant toute
            # écriture disque, pas nettoyée après coup.
            assert not outside_marker.exists()
            written_files = [p for p in root.rglob("*") if p.is_file()] if root.exists() else []
            assert written_files == []

    def test_open_stream_rejects_traversal_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "storage_root"
            storage = LocalDiskStorage(root)
            with pytest.raises(PathTraversalError):
                storage.open_stream("../../etc/passwd")

    def test_legitimate_content_addressed_key_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalDiskStorage(Path(tmp) / "storage_root")
            storage.put_bytes("hd/ab/abcdef.jpg", b"contenu legitime")
            assert storage.exists("hd/ab/abcdef.jpg")
