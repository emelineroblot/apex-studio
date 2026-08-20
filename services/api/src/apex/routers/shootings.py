"""`shooting` — CRUD, équipe affectée, engagements (clé métier du projet, §3-I, §3-F.3).

Cloisonnement photographe : `owner` voit tout, `photographer` uniquement ses shootings
affectés (`shooting_staff`) — via `services/access.py`. La création, la modification des
champs du shooting et l'affectation d'équipe restent `owner` uniquement (§3-I, matrice) ;
les engagements sont ouverts en écriture au photographe affecté.
"""

import csv
import io
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import ScalarSelect, Select, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apex.db import get_db
from apex.models.catalog import Client, Driver, Team
from apex.models.media import Media
from apex.models.shooting import Engagement, Shooting, ShootingStaff
from apex.schemas.common import Page
from apex.schemas.shooting import (
    EngagementCreate,
    EngagementImportError,
    EngagementImportResult,
    EngagementOut,
    ShootingCreate,
    ShootingOut,
    ShootingPatch,
    ShootingSummary,
    StaffMember,
    StaffUpdateRequest,
    StaffUpdateResponse,
)
from apex.security import CurrentUser, require_role
from apex.services import access

router = APIRouter(prefix="/shootings", tags=["shootings"])

DEFAULT_STAFF_ROLE = "member"


def _media_count_subquery(*, status_filter: bool = False) -> ScalarSelect[int]:
    stmt = select(func.count()).select_from(Media).where(Media.shooting_id == Shooting.id)
    if status_filter:
        stmt = stmt.where(Media.attachment_status == "engagement_attached")
    return stmt.correlate(Shooting).scalar_subquery()


def _to_summary(row: Any) -> ShootingSummary:
    shooting, media_count, attached_count = row
    return ShootingSummary(
        id=shooting.id,
        client_id=shooting.client_id,
        circuit_id=shooting.circuit_id,
        title=shooting.title,
        starts_at=shooting.starts_at,
        ends_at=shooting.ends_at,
        status=shooting.status,
        media_count=media_count,
        attached_count=attached_count,
    )


def _parse_query_datetime(value: str, *, param: str) -> datetime:
    """🟡 : `from`/`to` étaient passés bruts à SQLAlchemy — une valeur non parsable
    (ex. `from=n%27importe+quoi`) atteignait Postgres tel quel et levait un `DataError`
    non capturé, renvoyé en `500` plutôt qu'en `422`.
    """
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_datetime",
                "message": f"Paramètre « {param} » : date/heure ISO 8601 attendue.",
                "detail": {"param": param, "value": value},
            },
        ) from exc


@router.get("", response_model=Page[ShootingSummary], summary="Liste des shootings")
def list_shootings(
    user: CurrentUser,
    db: Session = Depends(get_db),
    client_id: int | None = None,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    status: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, le=100),
) -> Page[ShootingSummary]:
    stmt = select(Shooting, _media_count_subquery(), _media_count_subquery(status_filter=True))
    if not access.is_owner(user):
        stmt = stmt.where(Shooting.id.in_(access.visible_shooting_ids(user)))
    if client_id is not None:
        stmt = stmt.where(Shooting.client_id == client_id)
    if status is not None:
        stmt = stmt.where(Shooting.status == status)
    if from_ is not None:
        stmt = stmt.where(Shooting.starts_at >= _parse_query_datetime(from_, param="from"))
    if to is not None:
        stmt = stmt.where(Shooting.starts_at <= _parse_query_datetime(to, param="to"))
    if cursor is not None:
        try:
            after_id = int(cursor)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_cursor", "message": "Curseur invalide.", "detail": None},
            ) from exc
        stmt = stmt.where(Shooting.id > after_id)

    stmt = stmt.order_by(Shooting.id).limit(limit + 1)
    rows = db.execute(stmt).all()
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    next_cursor = str(page_rows[-1][0].id) if has_more and page_rows else None
    return Page(items=[_to_summary(r) for r in page_rows], next_cursor=next_cursor)


def _shooting_out(db: Session, shooting: Shooting) -> ShootingOut:
    staff = (
        db.execute(select(ShootingStaff).where(ShootingStaff.shooting_id == shooting.id))
        .scalars()
        .all()
    )
    engagement_count = db.execute(
        select(func.count()).select_from(Engagement).where(Engagement.shooting_id == shooting.id)
    ).scalar_one()
    return ShootingOut(
        id=shooting.id,
        client_id=shooting.client_id,
        circuit_id=shooting.circuit_id,
        title=shooting.title,
        starts_at=shooting.starts_at,
        ends_at=shooting.ends_at,
        status=shooting.status,
        quota_bytes=shooting.quota_bytes,
        notes=shooting.notes,
        staff=[StaffMember(user_id=s.user_id, role=s.role) for s in staff],
        engagement_count=engagement_count,
    )


@router.post(
    "",
    response_model=ShootingOut,
    status_code=201,
    summary="Créer un shooting",
    dependencies=[require_role("owner")],
)
def create_shooting(payload: ShootingCreate, db: Session = Depends(get_db)) -> ShootingOut:
    shooting = Shooting(
        client_id=payload.client_id,
        circuit_id=payload.circuit_id,
        title=payload.title,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        notes=payload.notes,
    )
    if payload.quota_bytes is not None:
        shooting.quota_bytes = payload.quota_bytes
    db.add(shooting)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_shooting",
                "message": "La plage horaire ou une référence est invalide.",
                # P1 (revue J1) : ne jamais renvoyer `str(exc.orig)` au client — le
                # message PostgreSQL brut peut exposer des noms de contrainte/colonne.
                "detail": None,
            },
        ) from exc
    db.refresh(shooting)
    return _shooting_out(db, shooting)


@router.get("/{shooting_id}", response_model=ShootingOut, summary="Fiche shooting")
def get_shooting(shooting_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> ShootingOut:
    shooting = access.get_visible_shooting_or_404(db, user, shooting_id)
    return _shooting_out(db, shooting)


@router.patch(
    "/{shooting_id}",
    response_model=ShootingOut,
    summary="Modifier un shooting",
    dependencies=[require_role("owner")],
)
def patch_shooting(
    shooting_id: int, payload: ShootingPatch, db: Session = Depends(get_db)
) -> ShootingOut:
    shooting = db.execute(select(Shooting).where(Shooting.id == shooting_id)).scalar_one_or_none()
    if shooting is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "Shooting introuvable.", "detail": None},
        )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(shooting, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_shooting",
                "message": "La plage horaire ou une référence est invalide.",
                # P1 (revue J1) : ne jamais renvoyer `str(exc.orig)` au client — le
                # message PostgreSQL brut peut exposer des noms de contrainte/colonne.
                "detail": None,
            },
        ) from exc
    db.refresh(shooting)
    return _shooting_out(db, shooting)


@router.put(
    "/{shooting_id}/staff",
    response_model=StaffUpdateResponse,
    summary="Affecter l'équipe au shooting",
    dependencies=[require_role("owner")],
)
def put_shooting_staff(
    shooting_id: int, payload: StaffUpdateRequest, db: Session = Depends(get_db)
) -> StaffUpdateResponse:
    shooting = db.execute(select(Shooting).where(Shooting.id == shooting_id)).scalar_one_or_none()
    if shooting is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "Shooting introuvable.", "detail": None},
        )
    db.execute(delete(ShootingStaff).where(ShootingStaff.shooting_id == shooting_id))
    for user_id in dict.fromkeys(payload.user_ids):  # dédoublonne en préservant l'ordre
        db.add(ShootingStaff(shooting_id=shooting_id, user_id=user_id, role=DEFAULT_STAFF_ROLE))
    db.commit()
    staff = (
        db.execute(select(ShootingStaff).where(ShootingStaff.shooting_id == shooting_id))
        .scalars()
        .all()
    )
    return StaffUpdateResponse(staff=[StaffMember(user_id=s.user_id, role=s.role) for s in staff])


@router.get(
    "/{shooting_id}/engagements",
    response_model=list[EngagementOut],
    summary="Engagements du shooting",
)
def list_engagements(
    shooting_id: int, user: CurrentUser, db: Session = Depends(get_db)
) -> list[EngagementOut]:
    access.get_visible_shooting_or_404(db, user, shooting_id)
    engagements = (
        db.execute(
            select(Engagement)
            .where(Engagement.shooting_id == shooting_id)
            .order_by(Engagement.car_number)
        )
        .scalars()
        .all()
    )
    return [EngagementOut.model_validate(e) for e in engagements]


@router.post(
    "/{shooting_id}/engagements",
    response_model=EngagementOut,
    status_code=201,
    summary="Créer un engagement",
)
def create_engagement(
    shooting_id: int, payload: EngagementCreate, user: CurrentUser, db: Session = Depends(get_db)
) -> EngagementOut:
    access.assert_can_write_engagements(db, user, shooting_id)
    engagement = Engagement(shooting_id=shooting_id, **payload.model_dump())
    db.add(engagement)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "duplicate_car_number",
                "message": f"Le numéro « {payload.car_number} » existe déjà sur ce shooting.",
                "detail": None,
            },
        ) from exc
    db.refresh(engagement)
    return EngagementOut.model_validate(engagement)


class _UnknownReferenceError(Exception):
    """Revue J1 (🟠) : l'import CSV contournait la matrice des rôles (§3-I) — un
    photographe, lecture seule sur le référentiel, pouvait créer des `Client`/`Driver`/
    `Team` en important un CSV mentionnant des noms inconnus. Levée par
    `_get_or_create_by_name(..., allow_create=False)` plutôt que de créer silencieusement.
    """

    def __init__(self, label: str, name: str) -> None:
        super().__init__(
            f"{label} inconnu : « {name} ». Seul le dirigeant peut créer une nouvelle fiche "
            "depuis un import."
        )


def _get_or_create_by_name(
    db: Session, model: type, name: str, *, extra: dict | None = None, allow_create: bool
) -> int:
    """Résolution CSV : les colonnes `driver`/`team`/`client` sont des **noms**, pas des id.

    Décision d'implémentation (non détaillée dans le plan) : *find-or-create* par nom exact,
    cohérent avec `AGENTS.md` (« l'environnement est jetable », pas de dédoublonnage manuel
    attendu pour un import de démonstration). Signalé en revue.

    `allow_create` (revue J1, 🟠) : `False` pour un photographe — seule la *résolution*
    d'un nom déjà connu lui reste ouverte, la *création* reste `owner` (matrice §3-I,
    « Clients, circuits, pilotes, écuries : lecture seule » pour `photographer`).
    """
    name_col = "full_name" if model is Driver else "name"
    stmt: Select[Any] = select(model).where(getattr(model, name_col) == name)
    existing = db.execute(stmt).scalar_one_or_none()
    if existing is not None:
        return int(existing.id)
    if not allow_create:
        raise _UnknownReferenceError(model.__name__, name)
    kwargs = {name_col: name, **(extra or {})}
    obj = model(**kwargs)
    db.add(obj)
    db.flush()
    return int(obj.id)


@router.post(
    "/{shooting_id}/engagements:import",
    response_model=EngagementImportResult,
    summary="Import CSV des engagements (`car_number,driver,team,client,car_model`)",
)
def import_engagements(
    shooting_id: int,
    user: CurrentUser,
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
) -> EngagementImportResult:
    access.assert_can_write_engagements(db, user, shooting_id)

    raw = file.file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_csv_encoding",
                "message": "Le fichier CSV doit être encodé en UTF-8.",
                "detail": None,
            },
        ) from exc

    reader = csv.DictReader(io.StringIO(text))
    required_columns = {"car_number", "driver", "team", "client", "car_model"}
    if reader.fieldnames is None or not required_columns.issubset(set(reader.fieldnames)):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_csv_header",
                "message": "Colonnes attendues : car_number,driver,team,client,car_model.",
                "detail": {"found": reader.fieldnames},
            },
        )

    existing_numbers = set(
        db.execute(
            select(Engagement.car_number).where(Engagement.shooting_id == shooting_id)
        ).scalars()
    )

    # Revue J1 (🟠) : la création de nouvelles fiches référentiel via l'import reste
    # réservée au dirigeant — un photographe ne peut résoudre que des noms déjà connus.
    allow_create_reference = access.is_owner(user)

    created = 0
    skipped = 0
    errors: list[EngagementImportError] = []

    for line_no, row in enumerate(reader, start=2):  # ligne 1 = en-tête
        car_number = (row.get("car_number") or "").strip()
        if not car_number:
            errors.append(
                EngagementImportError(line=line_no, message="Numéro de voiture manquant.")
            )
            continue
        if car_number in existing_numbers:
            skipped += 1
            continue

        # SAVEPOINT par ligne : une ligne en échec ne doit jamais annuler les lignes déjà
        # créées dans la même requête (`db.rollback()` global aurait défait tout l'import).
        try:
            with db.begin_nested():
                driver_id = None
                driver_name = (row.get("driver") or "").strip()
                if driver_name:
                    driver_id = _get_or_create_by_name(
                        db, Driver, driver_name, allow_create=allow_create_reference
                    )

                client_id = None
                client_name = (row.get("client") or "").strip()
                if client_name:
                    client_id = _get_or_create_by_name(
                        db,
                        Client,
                        client_name,
                        extra={"kind": "team"},
                        allow_create=allow_create_reference,
                    )

                team_id = None
                team_name = (row.get("team") or "").strip()
                if team_name:
                    team_id = _get_or_create_by_name(
                        db,
                        Team,
                        team_name,
                        extra={"client_id": client_id},
                        allow_create=allow_create_reference,
                    )

                car_model = (row.get("car_model") or "").strip() or None

                engagement = Engagement(
                    shooting_id=shooting_id,
                    car_number=car_number,
                    driver_id=driver_id,
                    team_id=team_id,
                    client_id=client_id,
                    car_model=car_model,
                )
                db.add(engagement)
                db.flush()
            existing_numbers.add(car_number)
            created += 1
        except IntegrityError as exc:
            errors.append(EngagementImportError(line=line_no, message=str(exc.orig)))
        except _UnknownReferenceError as exc:
            errors.append(EngagementImportError(line=line_no, message=str(exc)))

    db.commit()
    return EngagementImportResult(created=created, skipped=skipped, errors=errors)
