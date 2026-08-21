"""Fabriques minimales pour construire un jeu de recherche « à la main », calculable de
tête (§3-K.2, `tests/search/test_facets.py`). Pas de pipeline réel ici : on écrit
directement en base (`media`, `shooting`, `engagement`, …) puis on appelle
`services/search_projection.py::project_media_search` — exactement le même chemin que la
réindexation réelle, donc un test fidèle sans repasser par l'ingestion complète.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from apex.models.catalog import Camera, Circuit, Client, Driver, Team
from apex.models.media import Media, MediaEngagement, MediaSeries, UploadBatch
from apex.models.shooting import Engagement, Shooting
from apex.models.user import AppUser


def make_circuit(session: Session, name: str) -> Circuit:
    circuit = Circuit(name=name, city="Test", country="France")
    session.add(circuit)
    session.flush()
    return circuit


def make_client(session: Session, name: str) -> Client:
    client = Client(name=name, kind="team")
    session.add(client)
    session.flush()
    return client


def make_team(session: Session, name: str, client: Client) -> Team:
    team = Team(name=name, client_id=client.id)
    session.add(team)
    session.flush()
    return team


def make_driver(session: Session, name: str) -> Driver:
    driver = Driver(full_name=name)
    session.add(driver)
    session.flush()
    return driver


def make_camera(session: Session, model: str = "Test Camera") -> Camera:
    camera = Camera(model=model, make="Test")
    session.add(camera)
    session.flush()
    return camera


def make_shooting(
    session: Session, *, client: Client, circuit: Circuit, starts_at: datetime
) -> Shooting:
    shooting = Shooting(
        client_id=client.id,
        circuit_id=circuit.id,
        title=f"Shooting {circuit.name}",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=2),
        status="done",
    )
    session.add(shooting)
    session.flush()
    return shooting


def make_engagement(
    session: Session,
    *,
    shooting: Shooting,
    car_number: str,
    team: Team | None = None,
    driver: Driver | None = None,
    client: Client | None = None,
) -> Engagement:
    engagement = Engagement(
        shooting_id=shooting.id,
        car_number=car_number,
        team_id=team.id if team else None,
        driver_id=driver.id if driver else None,
        client_id=client.id if client else (team.client_id if team else None),
    )
    session.add(engagement)
    session.flush()
    return engagement


def make_upload_batch(session: Session, *, user: AppUser) -> UploadBatch:
    batch = UploadBatch(created_by=user.id, expected_count=0, status="closed")
    session.add(batch)
    session.flush()
    return batch


def make_media(
    session: Session,
    *,
    batch: UploadBatch,
    user: AppUser,
    shooting: Shooting | None = None,
    camera: Camera | None = None,
    shot_at: datetime,
    attachment_status: str = "unattached",
    attachment_source: str | None = None,
    ingest_status: str = "ingested",
    quarantine_reason: str | None = None,
    iso: int | None = None,
    focal_length: float | None = None,
    lens_model: str | None = None,
    caption: str | None = None,
    keywords: list[str] | None = None,
    is_series_representative: bool = True,
    series_id: int | None = None,
    duplicate_of_media_id: int | None = None,
    engagements: list[Engagement] | None = None,
    engagement_source: str = "ocr",
) -> Media:
    media = Media(
        batch_id=batch.id,
        uploaded_by=user.id,
        idempotency_key=f"test-{uuid4().hex}",
        original_filename="test.jpg",
        byte_size=1_000_000,
        ingest_status=ingest_status,
        quarantine_reason=quarantine_reason,
        shooting_id=shooting.id if shooting else None,
        camera_id=camera.id if camera else None,
        shot_at=shot_at,
        shot_at_exif=shot_at.replace(tzinfo=None),
        attachment_status=attachment_status,
        attachment_source=attachment_source,
        iso=iso,
        focal_length=focal_length,
        lens_model=lens_model,
        caption=caption,
        keywords=keywords,
        is_series_representative=is_series_representative,
        series_id=series_id,
        duplicate_of_media_id=duplicate_of_media_id,
    )
    session.add(media)
    session.flush()

    for engagement in engagements or []:
        session.add(
            MediaEngagement(
                media_id=media.id, engagement_id=engagement.id, source=engagement_source
            )
        )
    session.flush()
    return media


def make_media_series(
    session: Session,
    *,
    shooting: Shooting,
    camera: Camera | None,
    members: list[Media],
    representative: Media,
) -> MediaSeries:
    """Matérialise une série sur des médias **déjà créés** (`make_media`, `series_id=None`
    par défaut) — mêmes étapes que `pipeline/series.py::regroup_bursts_for_shooting`
    (créer la ligne `media_series`, puis rattacher chaque membre), pour un test qui n'a pas
    besoin de vraies images/rafales.
    """
    assert representative in members, "le représentant doit être un des membres"
    shot_ats = [m.shot_at for m in members if m.shot_at is not None]
    series = MediaSeries(
        shooting_id=shooting.id,
        camera_id=camera.id if camera else None,
        started_at=min(shot_ats),
        ended_at=max(shot_ats),
        representative_media_id=None,
        member_count=len(members),
    )
    session.add(series)
    session.flush()
    series.representative_media_id = representative.id
    for member in members:
        member.series_id = series.id
        member.is_series_representative = member.id == representative.id
    session.flush()
    return series


def as_ids(items: list[dict[str, Any]]) -> set[int]:
    return {int(item["id"]) for item in items}
