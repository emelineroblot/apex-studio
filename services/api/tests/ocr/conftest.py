"""Fixtures des tests OCR — base réelle, stockage réel, **moteur injectable**.

Le seul élément remplacé est le moteur (`set_engine`) : c'est précisément la frontière que
le principe DOE cherche à établir. Si toute la chaîne — persistance des candidats, jointure
sur les engagements, classification par seuils, file de validation, statistiques — se teste
avec un moteur factice de dix lignes, c'est que le jugement probabiliste est effectivement
isolé et que le reste est du code exact.

Un test (`test_ocr_media_handler.py::test_reads_a_real_synthetic_plate`) fait tourner le
**vrai** moteur sur une image réellement générée, pour que la frontière ne soit pas la seule
chose vérifiée.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from PIL import Image
from sqlalchemy.orm import Session

from apex.models.catalog import Circuit, Client, Driver, Team
from apex.models.media import Media, UploadBatch
from apex.models.search import MediaOcrCandidate
from apex.models.shooting import Engagement, Shooting
from apex.models.user import AppUser
from apex.pipeline.ocr import classify
from apex.pipeline.ocr.engine import TextBox, set_engine
from apex.services.ocr_settings import ENGINE_VERSION_DEFAULT
from apex.services.storage import get_storage_client
from tests.conftest import make_user


class FakeOcrEngine:
    """Moteur factice : rend des boîtes programmées et **compte ses appels**.

    Le compteur est le point du dispositif : plusieurs tests affirment qu'un changement de
    seuil ne déclenche aucune inférence. Sans compteur, cette affirmation ne serait qu'un
    commentaire.
    """

    def __init__(self, boxes: list[TextBox] | None = None) -> None:
        self.boxes = boxes or []
        self.calls = 0

    @property
    def version(self) -> str:
        return ENGINE_VERSION_DEFAULT

    def read(self, image: Image.Image) -> list[TextBox]:
        self.calls += 1
        return list(self.boxes)


class ExplodingOcrEngine:
    """Moteur qui refuse de lire — prouve qu'un chemin de code ne fait aucune inférence."""

    @property
    def version(self) -> str:
        return ENGINE_VERSION_DEFAULT

    def read(self, image: Image.Image) -> list[TextBox]:
        raise AssertionError(
            "Le moteur OCR a été appelé alors que ce chemin de code doit être "
            "purement déterministe (re-projection de candidats déjà persistés)."
        )


def centered_box(text: str, confidence: float, *, size: int = 200) -> TextBox:
    """Boîte plausible au centre d'un aperçu 1600×1067 : passe le filtrage géométrique."""
    x0, y0 = 700.0, 500.0
    x1, y1 = x0 + size, y0 + size * 0.9
    return TextBox(
        text=text,
        confidence=confidence,
        quad=((x0, y0), (x1, y0), (x1, y1), (x0, y1)),
    )


@pytest.fixture(autouse=True)
def _restore_engine() -> Iterator[None]:
    """Aucun test ne laisse un moteur injecté derrière lui."""
    yield
    set_engine(None)


@pytest.fixture
def fake_engine() -> FakeOcrEngine:
    engine = FakeOcrEngine()
    set_engine(engine)
    return engine


@pytest.fixture
def owner(db_session: Session) -> AppUser:
    return make_user(db_session, role="owner", email="owner-ocr@apex-test.dev")


@pytest.fixture
def shooting(db_session: Session, owner: AppUser) -> Shooting:
    """Un shooting et sa **table des engagements** — la clé métier du projet.

    Trois voitures au départ : 12 (Camille Roux / Écurie Chicane), 7 saisi « 07 » pour
    éprouver la canonicalisation, et 250. Le n°99 n'est volontairement **pas** engagé :
    c'est lui qui doit produire une incohérence, jamais un rattachement.
    """
    circuit = Circuit(name="Circuit des tests OCR", timezone="Europe/Paris")
    db_session.add(circuit)
    db_session.flush()

    now = datetime.now(UTC)
    shooting = Shooting(
        circuit_id=circuit.id,
        title="Meeting de test OCR",
        starts_at=now - timedelta(hours=2),
        ends_at=now + timedelta(hours=6),
    )
    db_session.add(shooting)
    db_session.flush()

    client = Client(name="Écurie Chicane", kind="team")
    driver_a = Driver(full_name="Camille Roux")
    driver_b = Driver(full_name="Sacha Vidal")
    db_session.add_all([client, driver_a, driver_b])
    db_session.flush()
    team = Team(name="Chicane Compétition", client_id=client.id)
    db_session.add(team)
    db_session.flush()

    db_session.add_all(
        [
            Engagement(
                shooting_id=shooting.id,
                car_number="12",
                driver_id=driver_a.id,
                team_id=team.id,
                client_id=client.id,
            ),
            Engagement(
                shooting_id=shooting.id,
                car_number="07",
                driver_id=driver_b.id,
                team_id=team.id,
                client_id=client.id,
            ),
            Engagement(shooting_id=shooting.id, car_number="250", client_id=client.id),
        ]
    )
    db_session.commit()
    db_session.refresh(shooting)
    return shooting


@pytest.fixture
def batch(db_session: Session, owner: AppUser, shooting: Shooting) -> UploadBatch:
    batch = UploadBatch(
        created_by=owner.id, shooting_hint_id=shooting.id, expected_count=0, status="open"
    )
    db_session.add(batch)
    db_session.commit()
    return batch


def make_media(
    session: Session,
    *,
    owner: AppUser,
    batch: UploadBatch,
    shooting: Shooting | None,
    key_suffix: str,
    preview_bytes: bytes | None = None,
) -> Media:
    """Média ingéré, prêt pour l'OCR. `preview_bytes` écrit un vrai objet en stockage."""
    preview_key = f"preview/test-{key_suffix}.webp" if preview_bytes is not None else None
    if preview_bytes is not None and preview_key is not None:
        get_storage_client().put_bytes(preview_key, preview_bytes, content_type="image/webp")

    media = Media(
        batch_id=batch.id,
        uploaded_by=owner.id,
        idempotency_key=f"idem-{key_suffix}",
        original_filename=f"{key_suffix}.jpg",
        byte_size=1024,
        mime="image/jpeg",
        width=1600,
        height=1067,
        storage_key_preview=preview_key,
        shot_at=datetime.now(UTC),
        ingest_status="ingested",
        attachment_status="shooting_attached" if shooting is not None else "unattached",
        attachment_source="pipeline_time" if shooting is not None else None,
        shooting_id=shooting.id if shooting is not None else None,
    )
    session.add(media)
    session.commit()
    session.refresh(media)
    return media


def add_candidate(
    session: Session,
    media: Media,
    *,
    number: str,
    score: float,
    raw_text: str | None = None,
    resolution: str = classify.RESOLUTION_ABSTAIN,
    engagement_id: int | None = None,
    resolved_by: int | None = None,
) -> MediaOcrCandidate:
    """Insère un candidat **brut**, comme si le moteur venait de le produire.

    Écrire directement les candidats est le raccourci qui rend ces tests instantanés — et
    c'est possible **parce que** la persistance des candidats est indépendante du moteur.
    C'est la même propriété qui rend `reclassify_ocr` gratuit en production.
    """
    candidate = MediaOcrCandidate(
        media_id=media.id,
        raw_text=raw_text or number,
        normalized_number=number,
        confidence=score,
        bbox={"x": 0.4, "y": 0.45, "w": 0.12, "h": 0.15, "image_width": 1600, "image_height": 1067},
        engine_version=ENGINE_VERSION_DEFAULT,
        resolution=resolution,
        engagement_id=engagement_id,
        resolved_by=resolved_by,
    )
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate
