"""Handler `ocr_media` — l'unique job qui appelle le modèle.

Un test fait tourner le **vrai** moteur RapidOCR sur une image réellement générée : c'est ce
qui distingue « la frontière DOE est bien posée » de « la frontière DOE est bien mockée ».
Les autres utilisent le moteur factice pour éprouver l'idempotence et les portes d'entrée.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image
from sqlalchemy import select

from apex.db import SessionLocal
from apex.demo.synthetic_plates import LEVELS, render_sample
from apex.models.media import MediaEngagement
from apex.models.search import MediaOcrCandidate
from apex.models.shooting import Engagement
from apex.pipeline.ocr import classify
from apex.pipeline.ocr.engine import set_engine
from apex.queue.enqueue import enqueue
from apex.queue.runner import drain
from apex.services.ocr_settings import OCR_HIGH_DEFAULT
from tests.ocr.conftest import add_candidate, centered_box, make_media


def _run_queue() -> None:
    drain(SessionLocal, "test-ocr-media", deadline=None, batch_size=10)


def _webp(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=90)
    return buffer.getvalue()


def _candidates(db_session, media):
    return list(
        db_session.execute(
            select(MediaOcrCandidate)
            .where(MediaOcrCandidate.media_id == media.id)
            .order_by(MediaOcrCandidate.id)
        ).scalars()
    )


class TestLectureReelle:
    def test_reads_a_real_synthetic_plate_end_to_end(self, db_session, owner, shooting, batch):
        """Vrai moteur, vraie image, vraie base : du pixel au rattachement métier.

        On rend une plaque nette, on **engage sa voiture** au shooting, et on attend un
        rattachement à cet engagement précis — sans qu'aucune ligne de code n'ait « décidé »
        du pilote : c'est une jointure SQL sur la table des engagements.
        """
        image, sample = _clean_plate()
        assert sample.number is not None
        engagement = Engagement(
            shooting_id=shooting.id, car_number=sample.number, driver_id=None, client_id=None
        )
        db_session.add(engagement)
        db_session.commit()

        media = make_media(
            db_session,
            owner=owner,
            batch=batch,
            shooting=shooting,
            key_suffix="real-12",
            preview_bytes=_webp(image),
        )

        enqueue(db_session, "ocr_media", {"media_id": media.id}, dedupe_key=f"ocr:{media.id}")
        db_session.commit()
        _run_queue()
        db_session.expire_all()

        candidates = _candidates(db_session, media)
        assert candidates, "le moteur n'a produit aucun candidat sur une plaque nette"
        numbers = {candidate.normalized_number for candidate in candidates}
        assert sample.number in numbers, f"lu {numbers}, attendu {sample.number}"

        winner = next(c for c in candidates if c.normalized_number == sample.number)
        assert winner.resolution == classify.RESOLUTION_AUTO
        assert float(winner.confidence) >= OCR_HIGH_DEFAULT
        assert winner.bbox["image_width"] == image.width
        assert winner.engagement_id == engagement.id

        links = list(
            db_session.execute(
                select(MediaEngagement).where(MediaEngagement.media_id == media.id)
            ).scalars()
        )
        assert len(links) == 1
        assert links[0].source == "ocr"
        assert links[0].engagement_id == engagement.id
        db_session.refresh(media)
        assert media.attachment_status == "engagement_attached"


def _clean_plate():
    """Une image du niveau le plus propre portant un numéro (pas un des cas « sans numéro »)."""
    level = LEVELS[0]
    for index in range(50):
        image, sample = render_sample(index, level, seed=20260821)
        if sample.number is not None:
            return image, sample
    raise AssertionError("aucune image synthétique exploitable au niveau 0")


class TestPortesDEntree:
    @pytest.mark.parametrize(
        ("mutation", "expected"),
        [
            (
                {"ingest_status": "quarantined", "quarantine_reason": "truncated_file"},
                "ingest_status=quarantined",
            ),
            ({"shooting_id": None, "attachment_status": "unattached"}, "no_shooting"),
        ],
    )
    def test_skips_what_it_must_not_read(
        self, db_session, owner, shooting, batch, fake_engine, mutation, expected
    ):
        """Ne pas dépenser d'inférence pour une lecture qui ne pourrait rien produire."""
        media = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix=f"skip-{expected}"
        )
        for field, value in mutation.items():
            setattr(media, field, value)
        db_session.commit()

        enqueue(db_session, "ocr_media", {"media_id": media.id}, dedupe_key=f"ocr:{media.id}")
        db_session.commit()
        _run_queue()

        assert fake_engine.calls == 0
        assert _candidates(db_session, media) == []

    def test_a_duplicate_is_not_read_twice(self, db_session, owner, shooting, batch, fake_engine):
        master = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="master"
        )
        duplicate = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="dupe"
        )
        duplicate.duplicate_of_media_id = master.id
        db_session.commit()

        enqueue(
            db_session, "ocr_media", {"media_id": duplicate.id}, dedupe_key=f"ocr:{duplicate.id}"
        )
        db_session.commit()
        _run_queue()

        assert fake_engine.calls == 0


class TestIdempotence:
    def test_replaying_the_job_converges_without_duplicating_candidates(
        self, db_session, owner, shooting, batch, fake_engine
    ):
        """§3-E.6 : rejouer un handler produit le même état final, sans effet de bord dupliqué."""
        fake_engine.boxes = [centered_box("12", 0.95)]
        image = Image.new("RGB", (1600, 1067), (40, 60, 90))
        media = make_media(
            db_session,
            owner=owner,
            batch=batch,
            shooting=shooting,
            key_suffix="idem",
            preview_bytes=_webp(image),
        )

        for _ in range(3):
            enqueue(db_session, "ocr_media", {"media_id": media.id}, dedupe_key=f"ocr:{media.id}")
            db_session.commit()
            _run_queue()
            db_session.expire_all()

        assert fake_engine.calls == 3
        assert len(_candidates(db_session, media)) == 1
        links = list(
            db_session.execute(
                select(MediaEngagement).where(MediaEngagement.media_id == media.id)
            ).scalars()
        )
        assert len(links) == 1

    def test_a_human_decision_is_never_erased_by_a_new_reading(
        self, db_session, owner, shooting, batch, fake_engine
    ):
        """Relancer l'OCR ne réécrit pas ce qu'un humain a tranché — jamais."""
        fake_engine.boxes = [centered_box("250", 0.99)]
        image = Image.new("RGB", (1600, 1067), (40, 60, 90))
        media = make_media(
            db_session,
            owner=owner,
            batch=batch,
            shooting=shooting,
            key_suffix="keep-human",
            preview_bytes=_webp(image),
        )
        rejected = add_candidate(
            db_session,
            media,
            number="12",
            score=0.55,
            resolution=classify.RESOLUTION_REJECTED,
            resolved_by=owner.id,
        )

        enqueue(db_session, "ocr_media", {"media_id": media.id}, dedupe_key=f"ocr:{media.id}")
        db_session.commit()
        _run_queue()
        db_session.expire_all()

        db_session.refresh(rejected)
        assert rejected.resolution == classify.RESOLUTION_REJECTED
        assert rejected.resolved_by == owner.id
        numbers = {candidate.normalized_number for candidate in _candidates(db_session, media)}
        assert numbers == {"12", "250"}


class TestEchecDeLecture:
    def test_a_missing_preview_never_quarantines_the_media(
        self, db_session, owner, shooting, batch, fake_engine
    ):
        """Un échec d'OCR n'est pas un problème de fichier : le média reste où il est.

        Le pipeline ne perd rien et ne ment pas : un `pipeline_event` motivé est écrit, le
        média garde son rattachement temporel, et personne ne se retrouve en quarantaine
        pour une lecture ratée.
        """
        media = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="nopreview"
        )
        media.storage_key_preview = "preview/absent-du-stockage.webp"
        db_session.commit()

        enqueue(db_session, "ocr_media", {"media_id": media.id}, dedupe_key=f"ocr:{media.id}")
        db_session.commit()
        _run_queue()
        db_session.expire_all()
        db_session.refresh(media)

        assert media.ingest_status == "ingested"
        assert media.attachment_status == "shooting_attached"
        assert fake_engine.calls == 0

        from apex.models.media import PipelineEvent

        events = list(
            db_session.execute(
                select(PipelineEvent).where(
                    PipelineEvent.media_id == media.id, PipelineEvent.step == "ocr"
                )
            ).scalars()
        )
        assert events and events[-1].status == "failed"
        assert "introuvable" in (events[-1].message or "")


def test_the_engine_is_replaceable_in_one_line(db_session, owner, shooting, batch):
    """La frontière DOE, vérifiée : tout le pipeline tourne avec un moteur de dix lignes.

    Si remplacer le moteur suffit à faire tourner la chaîne complète — persistance,
    jointure métier, seuils, rattachement — c'est que le jugement probabiliste est
    réellement isolé, et que le changer ne demandera pas de réécrire le jalon.
    """

    class TinyEngine:
        version = "tiny-1"

        def read(self, image):
            return [centered_box("250", 0.97)]

    set_engine(TinyEngine())
    image = Image.new("RGB", (1600, 1067), (10, 10, 10))
    media = make_media(
        db_session,
        owner=owner,
        batch=batch,
        shooting=shooting,
        key_suffix="tiny",
        preview_bytes=_webp(image),
    )
    enqueue(db_session, "ocr_media", {"media_id": media.id}, dedupe_key=f"ocr:{media.id}")
    db_session.commit()
    _run_queue()
    db_session.expire_all()

    [candidate] = _candidates(db_session, media)
    assert candidate.engine_version == "tiny-1"
    assert candidate.resolution == classify.RESOLUTION_AUTO
    db_session.refresh(media)
    assert media.attachment_status == "engagement_attached"
