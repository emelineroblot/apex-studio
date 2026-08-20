"""Cloisonnement des rôles (§3-I du plan) — **une seule porte**, empruntée par tous les
repositories/routeurs qui touchent à un shooting ou à un média.

Matrice appliquée (§3-I) :
- `owner` : lecture + écriture sur tout.
- `photographer` : lecture seule sur le référentiel (clients, circuits, pilotes, écuries) ;
  shootings/médias **limités à ceux où il est affecté** (`shooting_staff`) ; écriture
  autorisée uniquement sur les engagements et médias de ses propres shootings.

Convention de fuite d'information : une ressource hors périmètre renvoie **404**, jamais
`403` — un `403` révélerait son existence à un rôle qui ne devrait pas la voir (§3-I).
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import ColumnElement, Select, or_, select
from sqlalchemy.orm import Session

from apex.models.catalog import Camera
from apex.models.media import Media, UploadBatch
from apex.models.shooting import Shooting, ShootingStaff
from apex.models.user import AppUser


def is_owner(user: AppUser) -> bool:
    return user.role == "owner"


def _not_found(resource: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "not_found", "message": f"{resource} introuvable.", "detail": None},
    )


def require_owner(user: AppUser, *, message: str = "Réservé au rôle dirigeant.") -> None:
    if not is_owner(user):
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": message, "detail": None},
        )


def visible_shooting_ids(user: AppUser) -> Select[tuple[int]]:
    """Sous-requête (pas une liste Python, §3-I) des `shooting.id` visibles par `user`."""
    if is_owner(user):
        return select(Shooting.id)
    return select(ShootingStaff.shooting_id).where(ShootingStaff.user_id == user.id)


def shooting_visible(session: Session, user: AppUser, shooting_id: int) -> bool:
    if is_owner(user):
        return (
            session.execute(
                select(Shooting.id).where(Shooting.id == shooting_id)
            ).scalar_one_or_none()
            is not None
        )
    stmt = select(ShootingStaff.shooting_id).where(
        ShootingStaff.shooting_id == shooting_id, ShootingStaff.user_id == user.id
    )
    return session.execute(stmt).scalar_one_or_none() is not None


def get_visible_shooting_or_404(session: Session, user: AppUser, shooting_id: int) -> Shooting:
    stmt = select(Shooting).where(Shooting.id == shooting_id)
    if not is_owner(user):
        stmt = stmt.where(Shooting.id.in_(visible_shooting_ids(user)))
    shooting = session.execute(stmt).scalar_one_or_none()
    if shooting is None:
        raise _not_found("Shooting")
    return shooting


def can_write_engagements(session: Session, user: AppUser, shooting_id: int) -> bool:
    """Écriture des engagements : `owner` toujours, `photographer` seulement si affecté."""
    if is_owner(user):
        return True
    return shooting_visible(session, user, shooting_id)


def assert_can_write_engagements(session: Session, user: AppUser, shooting_id: int) -> None:
    if not can_write_engagements(session, user, shooting_id):
        raise _not_found("Shooting")


def media_visibility_clause(user: AppUser) -> ColumnElement[bool] | None:
    """Condition SQL à `.where()` sur une requête `Media` — jamais une liste Python.

    `owner` : aucune restriction. `photographer` : le média appartient à un de ses
    shootings, **ou** il l'a lui-même déposé (bac « à rattacher » avant tout rattachement,
    où `shooting_id IS NULL`) — sans cette clause, un photographe perdrait de vue ses
    propres imports tant qu'ils ne sont pas rattachés.
    """
    if is_owner(user):
        return None
    return or_(
        Media.shooting_id.in_(visible_shooting_ids(user)),
        Media.uploaded_by == user.id,
    )


def assert_can_read_media(session: Session, user: AppUser, media: Media) -> None:
    if is_owner(user):
        return
    if media.uploaded_by == user.id:
        return
    if media.shooting_id is not None and shooting_visible(session, user, media.shooting_id):
        return
    raise _not_found("Média")


def get_visible_media_or_404(session: Session, user: AppUser, media_id: int) -> Media:
    media = session.execute(select(Media).where(Media.id == media_id)).scalar_one_or_none()
    if media is None:
        raise _not_found("Média")
    assert_can_read_media(session, user, media)
    return media


def batch_visibility_clause(user: AppUser) -> ColumnElement[bool] | None:
    """Même logique que les médias, appliquée aux lots d'upload (`upload_batch`)."""
    if is_owner(user):
        return None
    return or_(
        UploadBatch.shooting_hint_id.in_(visible_shooting_ids(user)),
        UploadBatch.created_by == user.id,
    )


def assert_can_read_batch(session: Session, user: AppUser, batch: UploadBatch) -> None:
    if is_owner(user):
        return
    if batch.created_by == user.id:
        return
    if batch.shooting_hint_id is not None and shooting_visible(
        session, user, batch.shooting_hint_id
    ):
        return
    raise _not_found("Lot")


def camera_visibility_clause(user: AppUser) -> ColumnElement[bool] | None:
    """Condition SQL à `.where()` sur une requête `Camera` (revue J1, 🔴 n°6 : `/cameras`
    n'était cloisonné pour aucun rôle — un photographe pouvait lister **et** muter le
    boîtier de n'importe quel collègue).

    `owner` : aucune restriction. `photographer` : le boîtier lui est explicitement
    affecté (`Camera.owner_user_id`), **ou** il apparaît dans des médias qu'il peut déjà
    voir (`media_visibility_clause`) — un boîtier découvert automatiquement à l'ingestion
    (`exif.resolve_camera`, `owner_user_id IS NULL`) reste ajustable par le photographe qui
    a déposé les photos concernées, sans quoi le critère d'acceptation « un décalage
    d'horloge corrige rétroactivement le rattachement » serait bloqué derrière le rôle
    dirigeant sans que la matrice §3-I ne l'exige.
    """
    if is_owner(user):
        return None
    media_clause = media_visibility_clause(user)
    visible_media_cameras = select(Media.camera_id).where(Media.camera_id.is_not(None))
    if media_clause is not None:
        visible_media_cameras = visible_media_cameras.where(media_clause)
    return or_(Camera.owner_user_id == user.id, Camera.id.in_(visible_media_cameras))


def assert_can_mutate_camera(session: Session, user: AppUser, camera: Camera) -> None:
    """Garde de `PATCH /cameras/{id}` (revue J1, 🔴 n°6) — même logique que la lecture,
    appliquée en Python sur une seule ligne déjà chargée plutôt qu'en sous-requête.
    """
    if is_owner(user):
        return
    if camera.owner_user_id == user.id:
        return
    stmt = select(Media.camera_id).where(Media.camera_id.is_not(None))
    media_clause = media_visibility_clause(user)
    if media_clause is not None:
        stmt = stmt.where(media_clause)
    visible_ids = set(session.execute(stmt).scalars())
    if camera.id in visible_ids:
        return
    raise _not_found("Boîtier")
