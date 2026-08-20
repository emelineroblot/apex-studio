"""Hash exact du contenu (§3-G.1) — BLAKE2b-256, calculé en flux par blocs de 1 Mo.

Sert deux fois : détection de doublon **et** clé de stockage content-addressed (§3-H.2) —
deux fichiers identiques n'occupent qu'un seul objet `hd/`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

CHUNK_SIZE = 1024 * 1024
DIGEST_SIZE = 32


def hash_chunks(chunks: Iterable[bytes]) -> bytes:
    """Hash BLAKE2b-256 d'un flux de blocs — jamais tout le fichier en une fois."""
    digest = hashlib.blake2b(digest_size=DIGEST_SIZE)
    for chunk in chunks:
        digest.update(chunk)
    return digest.digest()


def hash_bytes(data: bytes) -> bytes:
    """Confort pour un buffer déjà en mémoire (taille bornée par `MAX_UPLOAD_BYTES`)."""

    def _chunks() -> Iterable[bytes]:
        for offset in range(0, len(data), CHUNK_SIZE):
            yield data[offset : offset + CHUNK_SIZE]

    return hash_chunks(_chunks())
