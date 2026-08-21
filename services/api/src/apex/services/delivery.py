"""Construction de l'archive de livraison (§3-M du plan).

**En flux, jamais en mémoire ni en fichier temporaire.** `zipstream-ng` produit les octets
de l'archive au fil de l'eau, chaque entrée alimentée par le flux de l'objet HD : la
mémoire consommée reste de l'ordre de quelques Mo, que la collection pèse 50 Mo ou 5 Go.
Un `/tmp` serverless est limité et éphémère, et un client qui attend la fin de la
construction avant le premier octet croit que rien ne se passe.

**`ZIP_STORED`, jamais `ZIP_DEFLATE`** : des JPEG sont déjà compressés — les recompresser
coûte du CPU pour un gain proche de zéro. Et le mode « stocké » permet de calculer la
taille exacte de l'archive **à l'avance**, donc d'annoncer un `Content-Length` : le
navigateur affiche une vraie barre de progression au lieu d'un compteur qui tourne.

Au-delà de `zip_stream_max_items` (défaut 200), l'archive est construite **une fois** par
le worker et déposée sur le stockage objet : passé ce volume, la probabilité qu'un flux de
plusieurs minutes casse — et doive être repris de zéro, faute de reprise par plage —
dépasse le coût du stockage temporaire.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session
from zipstream import ZIP_STORED, ZipStream

from apex.models.billing import Delivery, SelectionItem
from apex.models.media import Media
from apex.models.search import MediaSearch
from apex.services.app_settings import get_setting
from apex.services.storage import StorageClient

ZIP_STREAM_MAX_ITEMS_KEY = "zip_stream_max_items"
ZIP_STREAM_MAX_ITEMS_DEFAULT = 200


class MissingOriginalError(Exception):
    """Un fichier HD manque à l'appel — la livraison échoue **bruyamment**.

    Livrer une archive incomplète sans le dire serait exactement le « rejet silencieux »
    que le projet s'interdit : le client paierait une sélection dont il ne recevrait
    qu'une partie, sans que personne ne s'en aperçoive.
    """

    def __init__(self, media_id: int) -> None:
        super().__init__(f"média {media_id} : fichier haute définition introuvable")
        self.media_id = media_id


def get_zip_stream_max_items(session: Session) -> int:
    return int(get_setting(session, ZIP_STREAM_MAX_ITEMS_KEY, ZIP_STREAM_MAX_ITEMS_DEFAULT))


def selected_media(session: Session, selection_id: int) -> list[Media]:
    """Médias de la sélection, dans l'ordre de prise de vue — l'ordre dans lequel le
    photographe et le client les ont vus, jamais l'ordre d'insertion en base."""
    rows = (
        session.execute(
            select(Media)
            .join(SelectionItem, SelectionItem.media_id == Media.id)
            .where(SelectionItem.selection_id == selection_id)
            .order_by(Media.shot_at, Media.id)
        )
        .scalars()
        .all()
    )
    return list(rows)


def entry_name(position: int, media: Media, car_numbers: list[str]) -> str:
    """`0001-42-1234.jpg` — rang, numéro de voiture, identifiant.

    Le rang en tête pour que l'ordre chronologique survive à un explorateur de fichiers
    qui trie par nom ; l'identifiant en queue pour qu'aucun nom ne puisse entrer en
    collision, même si deux photos partagent le même numéro à la même seconde.
    """
    number = car_numbers[0] if car_numbers else "sans-numero"
    return f"{position:04d}-{number}-{media.id}.jpg"


def build_zip_stream(session: Session, storage: StorageClient, selection_id: int) -> ZipStream:
    """Compose l'archive **sans lire un seul octet d'image**.

    Chaque entrée reçoit une fonction génératrice — appelée seulement quand l'archive est
    réellement parcourue — et sa taille connue d'avance, ce qui rend `len(stream)` exact.
    """
    media_list = selected_media(session, selection_id)
    numbers = _car_numbers(session, [media.id for media in media_list])

    stream = ZipStream(compress_type=ZIP_STORED, sized=True)
    for position, media in enumerate(media_list, start=1):
        if media.storage_key_hd is None:
            raise MissingOriginalError(media.id)
        size = storage.object_size(media.storage_key_hd)
        if size is None:
            raise MissingOriginalError(media.id)
        stream.add(
            _lazy_chunks(storage, media.storage_key_hd),
            entry_name(position, media, numbers.get(media.id, [])),
            size=size,
        )
    return stream


def _lazy_chunks(storage: StorageClient, key: str) -> Iterator[bytes]:
    """Générateur paresseux : rien n'est lu tant que l'archive n'est pas parcourue, et
    seul le morceau courant vit en mémoire."""

    def _iterator() -> Iterator[bytes]:
        yield from storage.open_stream(key).chunks

    return _iterator()


def _car_numbers(session: Session, media_ids: list[int]) -> dict[int, list[str]]:
    if not media_ids:
        return {}
    rows = session.execute(
        select(MediaSearch.media_id, MediaSearch.car_numbers).where(
            MediaSearch.media_id.in_(media_ids)
        )
    ).all()
    return {row.media_id: list(row.car_numbers or []) for row in rows}


def archive_filename(client_name: str, collection_title: str) -> str:
    """Nom de fichier proposé au navigateur — ASCII, sans espace ni séparateur de chemin.

    Un `Content-Disposition` mal formé (accent non encodé, guillemet, barre oblique) casse
    le téléchargement chez certains navigateurs plutôt que de dégrader le nom.
    """
    import unicodedata

    def _slug(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value)
        ascii_only = "".join(c for c in decomposed if 32 <= ord(c) < 127)
        kept = [c if (c.isalnum() or c in "-_") else "-" for c in ascii_only]
        return "-".join(part for part in "".join(kept).split("-") if part).lower() or "collection"

    return f"{_slug(client_name)}-{_slug(collection_title)}.zip"


def stored_archive_key(delivery: Delivery) -> str:
    return f"delivery/{delivery.collection_id}/{delivery.id}.zip"
