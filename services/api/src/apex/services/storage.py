"""Stockage objet (§3-H du plan) — clés **content-addressed**, jamais d'URL présignée.

Deux implémentations d'une même interface `StorageClient` :
- `S3Storage` (boto3, S3-compatible — Cloudflare R2 en production, §3-H.1) ;
- `LocalDiskStorage` (disque local) — **prescrit explicitement pour le développement et
  les tests** : sans elle, rien n'est testable sans compte Cloudflare (aucun mock de
  stockage, §5 du plan : « stockage objet réel ou implémentation locale de `StorageClient`
  sur disque, même interface, mêmes clés »).

Organisation des clés (§3-H.2) :
```
incoming/{batch_id}/{idempotency_key}      # zone de dépôt, éphémère — pas de champ media
                                            # dédié : la clé se reconstruit depuis
                                            # (batch_id, idempotency_key), UNIQUE en base.
hd/{hash[0:2]}/{hash}.jpg
preview/{hash[0:2]}/{hash}.webp
thumb/{hash[0:2]}/{hash}.webp
deliveries/{delivery_id}.zip               # J3
```

Sélection du backend par `STORAGE_BACKEND` (`local` par défaut en dev, `s3` en prod) —
voir `apex/config.py`.
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import IO, Any

from apex.config import settings


class StorageError(Exception):
    """Erreur de stockage générique — jamais avalée silencieusement par les appelants."""


class ObjectNotFoundError(StorageError):
    def __init__(self, key: str) -> None:
        super().__init__(f"Objet introuvable : « {key} ».")
        self.key = key


@dataclass(slots=True)
class ObjectBody:
    """Corps d'un objet lu — toujours consommé en flux (§3-H.3), jamais chargé entier."""

    chunks: Iterator[bytes]
    content_length: int
    content_type: str | None


def incoming_key(batch_id: int, idempotency_key: str) -> str:
    return f"incoming/{batch_id}/{idempotency_key}"


def content_addressed_key(variant: str, content_hash_hex: str, ext: str) -> str:
    """`hd/{hash[0:2]}/{hash}.jpg`, `preview/{hash[0:2]}/{hash}.webp`, etc. (§3-H.2)."""
    return f"{variant}/{content_hash_hex[:2]}/{content_hash_hex}.{ext}"


class StorageClient(ABC):
    """Interface commune — le pipeline et les routeurs ne connaissent qu'elle."""

    @abstractmethod
    def put_stream(self, key: str, stream: IO[bytes], *, content_type: str | None = None) -> int:
        """Écrit le flux à `key`, renvoie le nombre d'octets écrits."""

    @abstractmethod
    def put_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        """Écrit `data` à `key` — utilisé pour les dérivés (déjà en mémoire, taille bornée)."""

    @abstractmethod
    def open_stream(self, key: str) -> ObjectBody:
        """Lit `key` en flux — lève `ObjectNotFoundError` si absent."""

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def object_size(self, key: str) -> int | None:
        """`None` si l'objet n'existe pas — jamais une exception pour ce cas précis."""

    @abstractmethod
    def list_prefix(self, prefix: str) -> Iterator[str]:
        """Liste les clés sous `prefix` — utilisé par `sweep_orphans` (§3-F.4.6)."""

    @abstractmethod
    def object_last_modified(self, key: str) -> datetime | None:
        """Date de dernière écriture — `sweep_orphans` ne quarantaine qu'un objet « âgé »
        (> 1 h, §3-F.4.6), pour laisser le temps à un upload en cours de se terminer.
        """

    @abstractmethod
    def delete(self, key: str) -> None:
        """Réservé aux tests / au nettoyage explicite — **jamais appelé par le pipeline**
        (invariant `AGENTS.md` : aucun média n'est jamais supprimé).
        """


class LocalDiskStorage(StorageClient):
    """Stockage sur disque — même interface, mêmes clés que le S3-compatible (§5 du plan)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # `key` est toujours un chemin relatif construit par notre propre code
        # (content-addressed ou `incoming/{batch_id}/{idempotency_key}`) — jamais dérivé
        # d'une entrée utilisateur brute sans passer par nos constructeurs de clé.
        return self.root / key

    def put_stream(self, key: str, stream: IO[bytes], *, content_type: str | None = None) -> int:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".part")
        written = 0
        with tmp_path.open("wb") as out:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                out.write(chunk)
                written += len(chunk)
        tmp_path.replace(path)  # écriture atomique côté disque local
        return written

    def put_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".part")
        tmp_path.write_bytes(data)
        tmp_path.replace(path)

    def open_stream(self, key: str) -> ObjectBody:
        path = self._path(key)
        if not path.is_file():
            raise ObjectNotFoundError(key)
        size = path.stat().st_size

        def _iter_chunks(chunk_size: int = 65536) -> Iterator[bytes]:
            with path.open("rb") as fh:
                yield from iter(lambda: fh.read(chunk_size), b"")

        return ObjectBody(chunks=_iter_chunks(), content_length=size, content_type=None)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def object_size(self, key: str) -> int | None:
        path = self._path(key)
        return path.stat().st_size if path.is_file() else None

    def list_prefix(self, prefix: str) -> Iterator[str]:
        base = self._path(prefix)
        if not base.exists():
            return
        for path in base.rglob("*"):
            if path.is_file() and not path.name.endswith(".part"):
                yield str(path.relative_to(self.root)).replace("\\", "/")

    def object_last_modified(self, key: str) -> datetime | None:
        path = self._path(key)
        if not path.is_file():
            return None
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            path.unlink()

    def wipe_all(self) -> None:
        """Réservé aux tests : vide entièrement la racine locale."""
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True, exist_ok=True)


class S3Storage(StorageClient):
    """Backend S3-compatible (Cloudflare R2, §3-H.1) — via `boto3`."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        region: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
    ) -> None:
        import boto3

        self.bucket = bucket
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )

    def put_stream(self, key: str, stream: IO[bytes], *, content_type: str | None = None) -> int:
        extra = {"ContentType": content_type} if content_type else {}
        self._client.upload_fileobj(stream, self.bucket, key, ExtraArgs=extra or None)
        head = self._client.head_object(Bucket=self.bucket, Key=key)
        return int(head["ContentLength"])

    def put_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        kwargs: dict[str, Any] = {"Bucket": self.bucket, "Key": key, "Body": data}
        if content_type:
            kwargs["ContentType"] = content_type
        self._client.put_object(**kwargs)

    def open_stream(self, key: str) -> ObjectBody:
        from botocore.exceptions import ClientError

        try:
            resp = self._client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"NoSuchKey", "404"}:
                raise ObjectNotFoundError(key) from exc
            raise StorageError(str(exc)) from exc

        body = resp["Body"]
        return ObjectBody(
            chunks=body.iter_chunks(65536),
            content_length=int(resp.get("ContentLength", 0)),
            content_type=resp.get("ContentType"),
        )

    def exists(self, key: str) -> bool:
        return self.object_size(key) is not None

    def object_size(self, key: str) -> int | None:
        from botocore.exceptions import ClientError

        try:
            head = self._client.head_object(Bucket=self.bucket, Key=key)
        except ClientError:
            return None
        return int(head["ContentLength"])

    def list_prefix(self, prefix: str) -> Iterator[str]:
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                yield str(obj["Key"])

    def object_last_modified(self, key: str) -> datetime | None:
        from botocore.exceptions import ClientError

        try:
            head = self._client.head_object(Bucket=self.bucket, Key=key)
        except ClientError:
            return None
        last_modified = head.get("LastModified")
        return last_modified if isinstance(last_modified, datetime) else None

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)


@lru_cache
def get_storage_client() -> StorageClient:
    """Instance mise en cache — sélectionnée par `STORAGE_BACKEND` (§3-H.1, décision A.5)."""
    if settings.storage_backend == "s3":
        return S3Storage(
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            bucket=settings.s3_bucket,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
        )
    return LocalDiskStorage(settings.storage_local_dir)
