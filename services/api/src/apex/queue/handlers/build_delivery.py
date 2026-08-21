"""Handler `build_delivery` (§3-M, registre §3-E.3) — prépare l'archive d'une sélection
validée.

Ce que ce job fait **vraiment**, et c'est plus modeste qu'il n'y paraît : il vérifie que
chaque fichier HD est bien là, calcule le nombre d'entrées et la taille exacte de
l'archive, puis passe la livraison à `ready`. En chemin nominal, **il n'écrit aucun
octet** : l'archive est produite à la volée quand le client la télécharge (§3-M, Option 2).

Il ne dépose une archive sur le stockage objet qu'au-delà de `zip_stream_max_items` —
passé ce volume, un flux de plusieurs minutes a trop de chances de casser, et il n'existe
pas de reprise par plage sur une archive générée en direct.

Vérifier les fichiers **avant** d'annoncer la livraison prête, plutôt que de le découvrir
au milieu du téléchargement, c'est la différence entre un message clair côté studio et un
fichier `.zip` tronqué chez le client.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from apex.models.billing import Delivery
from apex.models.job import Job
from apex.queue.registry import JobContext, handler
from apex.services import delivery as delivery_service
from apex.services.storage import get_storage_client


def _fail(session_delivery: Delivery, message: str) -> None:
    session_delivery.status = "failed"
    session_delivery.error = message


def _on_dead(session: Session, job: Job) -> None:
    """Un job mort ne doit jamais laisser une livraison bloquée en `building`.

    Sans ce hook, le client verrait un écran de préparation tourner indéfiniment, et le
    studio n'aurait aucune trace de l'échec (§3-E.5, « aucun job mort ne laisse un objet
    métier dans un état intermédiaire »).
    """
    delivery_id = (job.payload or {}).get("delivery_id")
    if delivery_id is None:
        return
    row = session.get(Delivery, int(delivery_id))
    if row is not None and row.status != "ready":
        _fail(row, job.last_error or "préparation interrompue")


@handler("build_delivery", max_attempts=3, on_dead=_on_dead)
def handle_build_delivery(ctx: JobContext) -> dict[str, Any]:
    delivery_id = ctx.job.payload.get("delivery_id")
    if delivery_id is None:
        raise ValueError("payload invalide : « delivery_id » manquant.")

    row = ctx.session.get(Delivery, int(delivery_id))
    if row is None:
        raise ValueError(f"livraison {delivery_id} introuvable")

    row.status = "building"
    row.error = None
    ctx.session.flush()
    ctx.heartbeat()

    storage = get_storage_client()
    try:
        stream = delivery_service.build_zip_stream(ctx.session, storage, row.selection_id)
    except delivery_service.MissingOriginalError as exc:
        # Échec **métier**, pas technique : réessayer trois fois ne fera pas réapparaître
        # un fichier absent. On consigne et on s'arrête là.
        _fail(row, str(exc))
        ctx.session.commit()
        return {"delivery_id": row.id, "status": "failed", "reason": "missing_original"}

    item_count = stream.num_queued()
    byte_size = len(stream)
    threshold = delivery_service.get_zip_stream_max_items(ctx.session)

    if item_count > threshold:
        # Grosse collection : on paie une fois le stockage plutôt que de risquer un flux
        # de plusieurs minutes irrécupérable. Une seule passe, en flux de bout en bout —
        # l'archive ne tient jamais entière ni en mémoire ni sur le disque du worker.
        key = delivery_service.stored_archive_key(row)
        storage.put_stream(
            key,
            _ZipReader(stream, ctx.heartbeat),  # type: ignore[arg-type]
            content_type="application/zip",
        )
        row.storage_key = key

    row.item_count = item_count
    row.byte_size = byte_size
    row.built_at = datetime.now(UTC)
    row.status = "ready"
    ctx.session.commit()
    return {"delivery_id": row.id, "item_count": item_count, "byte_size": byte_size}


class _ZipReader:
    """Adaptateur `read(n)` au-dessus d'un `ZipStream`, pour `storage.put_stream`.

    `put_stream` attend un objet à lire ; `ZipStream` est un itérable. Ce tampon fait le
    pont sans jamais garder plus d'un morceau que ce qui vient d'être demandé — c'est ce
    qui préserve la propriété centrale de §3-M : mémoire bornée, indépendante de la taille
    de la collection.

    Le heartbeat est rafraîchi au fil de la lecture : une archive de plusieurs gigaoctets
    dépasse largement les trois minutes de `STALE_AFTER`, et un `reap_stale` concurrent
    déclarerait ce worker mort en plein travail (§3-E.5).
    """

    #: ~8 Mo entre deux battements : assez rare pour ne rien coûter, assez fréquent pour
    #: tenir même sur un lien de stockage lent.
    HEARTBEAT_EVERY_BYTES = 8 * 1024 * 1024

    def __init__(self, stream: Iterable[bytes], heartbeat: Callable[[], None]) -> None:
        self._iterator = iter(stream)
        self._buffer = bytearray()
        self._heartbeat = heartbeat
        self._since_heartbeat = 0

    def read(self, size: int = -1) -> bytes:
        while size < 0 or len(self._buffer) < size:
            try:
                piece = next(self._iterator)
            except StopIteration:
                break
            self._buffer.extend(piece)
            self._since_heartbeat += len(piece)
            if self._since_heartbeat >= self.HEARTBEAT_EVERY_BYTES:
                self._since_heartbeat = 0
                self._heartbeat()
        if size < 0 or len(self._buffer) <= size:
            chunk, self._buffer = bytes(self._buffer), bytearray()
            return chunk
        chunk = bytes(self._buffer[:size])
        del self._buffer[:size]
        return chunk
