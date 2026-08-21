"""Classification et re-projection — **les critères d'acceptation J2 verrouillés**.

Base PostgreSQL réelle, aucun mock. Le moteur, lui, n'est jamais appelé : tous ces tests
partent de candidats **déjà persistés**, ce qui est exactement la situation de production
quand on change un seuil.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from apex.models.media import Media, MediaEngagement
from apex.models.search import MediaOcrCandidate
from apex.models.shooting import Engagement, Shooting
from apex.pipeline.ocr import classify
from apex.services.ocr_settings import (
    OCR_HIGH_KEY,
    OCR_LOW_KEY,
    load_ocr_settings,
    write_ocr_settings,
)
from tests.ocr.conftest import add_candidate, make_media


def _engagement(db: Session, shooting: Shooting, car_number: str) -> Engagement:
    return db.execute(
        select(Engagement).where(
            Engagement.shooting_id == shooting.id, Engagement.car_number == car_number
        )
    ).scalar_one()


def _links(db: Session, media: Media) -> list[MediaEngagement]:
    return list(
        db.execute(
            select(MediaEngagement)
            .where(MediaEngagement.media_id == media.id)
            .order_by(MediaEngagement.engagement_id)
        ).scalars()
    )


class TestRecoupementMetier:
    def test_a_confident_reading_of_an_engaged_car_is_attached(
        self, db_session, owner, shooting, batch
    ):
        media = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="auto"
        )
        add_candidate(db_session, media, number="12", score=0.94)

        classify.project_media(db_session, media, load_ocr_settings(db_session))
        db_session.commit()
        db_session.refresh(media)

        [link] = _links(db_session, media)
        assert link.engagement_id == _engagement(db_session, shooting, "12").id
        assert link.source == "ocr"
        assert link.created_by is None, "aucun humain n'est intervenu : traçabilité machine"
        assert media.attachment_status == "engagement_attached"
        assert media.attachment_source == "pipeline_ocr"

    def test_leading_zeros_do_not_break_the_join(self, db_session, owner, shooting, batch):
        """Le n°7 lu, saisi « 07 » à la table des engagements : c'est la même voiture."""
        media = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="zero"
        )
        add_candidate(db_session, media, number="7", score=0.95)

        classify.project_media(db_session, media, load_ocr_settings(db_session))
        db_session.commit()

        [link] = _links(db_session, media)
        assert link.engagement_id == _engagement(db_session, shooting, "07").id

    def test_a_number_absent_from_the_entry_list_is_never_force_attached(
        self, db_session, owner, shooting, batch
    ):
        """Critère d'acceptation J2 : incohérence signalée, **jamais** rattachée de force."""
        media = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="ghost"
        )
        # Le n°99 ne figure pas au plateau, et pourtant le modèle en est certain.
        add_candidate(db_session, media, number="99", score=0.995)

        classify.project_media(db_session, media, load_ocr_settings(db_session))
        db_session.commit()
        db_session.refresh(media)

        candidate = db_session.execute(
            select(MediaOcrCandidate).where(MediaOcrCandidate.media_id == media.id)
        ).scalar_one()
        assert candidate.resolution == classify.RESOLUTION_NOT_ENGAGED
        assert candidate.engagement_id is None
        assert _links(db_session, media) == [], "aucun rattachement ne doit exister"
        assert media.attachment_status == "inconsistent"

    def test_a_photo_can_carry_two_attachments(self, db_session, owner, shooting, batch):
        """Critère d'acceptation J2 : deux voitures dans le cadre, deux rattachements."""
        media = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="duo"
        )
        add_candidate(db_session, media, number="12", score=0.93)
        add_candidate(db_session, media, number="250", score=0.88)

        classify.project_media(db_session, media, load_ocr_settings(db_session))
        db_session.commit()
        db_session.refresh(media)

        links = _links(db_session, media)
        assert len(links) == 2
        assert {link.engagement_id for link in links} == {
            _engagement(db_session, shooting, "12").id,
            _engagement(db_session, shooting, "250").id,
        }
        assert media.attachment_status == "engagement_attached"

    def test_mid_confidence_goes_to_the_review_queue_without_attaching(
        self, db_session, owner, shooting, batch
    ):
        media = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="mid"
        )
        add_candidate(db_session, media, number="12", score=0.60)

        classify.project_media(db_session, media, load_ocr_settings(db_session))
        db_session.commit()
        db_session.refresh(media)

        candidate = db_session.execute(
            select(MediaOcrCandidate).where(MediaOcrCandidate.media_id == media.id)
        ).scalar_one()
        assert candidate.resolution == classify.RESOLUTION_REVIEW
        assert candidate.engagement_id is not None, "l'engagement est suggéré, pas appliqué"
        assert _links(db_session, media) == []
        assert media.attachment_status == "pending_review"

    def test_low_confidence_abstains_and_leaves_the_media_where_it_was(
        self, db_session, owner, shooting, batch
    ):
        media = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="low"
        )
        add_candidate(db_session, media, number="12", score=0.20)

        classify.project_media(db_session, media, load_ocr_settings(db_session))
        db_session.commit()
        db_session.refresh(media)

        assert _links(db_session, media) == []
        assert media.attachment_status == "shooting_attached"
        assert media.attachment_source == "pipeline_time"

    def test_a_media_without_shooting_cannot_be_judged(self, db_session, owner, batch):
        """Sans table des engagements, un numéro ne veut rien dire : on s'abstient."""
        media = make_media(db_session, owner=owner, batch=batch, shooting=None, key_suffix="orphan")
        add_candidate(db_session, media, number="12", score=0.99)

        classify.project_media(db_session, media, load_ocr_settings(db_session))
        db_session.commit()
        db_session.refresh(media)

        candidate = db_session.execute(
            select(MediaOcrCandidate).where(MediaOcrCandidate.media_id == media.id)
        ).scalar_one()
        assert candidate.resolution == classify.RESOLUTION_ABSTAIN
        assert _links(db_session, media) == []
        assert media.attachment_status == "unattached"


class TestRedistributionParLesSeuils:
    """« Changer les seuils redistribue les cas » — **sans jamais relancer l'inférence**."""

    def test_raising_the_high_threshold_moves_an_auto_to_review_and_detaches_it(
        self, db_session, owner, shooting, batch
    ):
        media = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="slide"
        )
        add_candidate(db_session, media, number="12", score=0.85)

        classify.project_media(db_session, media, load_ocr_settings(db_session))
        db_session.commit()
        assert len(_links(db_session, media)) == 1

        write_ocr_settings(db_session, {OCR_HIGH_KEY: 0.90, OCR_LOW_KEY: 0.45}, updated_by=owner.id)
        db_session.commit()
        classify.project_media(db_session, media, load_ocr_settings(db_session))
        db_session.commit()
        db_session.refresh(media)

        candidate = db_session.execute(
            select(MediaOcrCandidate).where(MediaOcrCandidate.media_id == media.id)
        ).scalar_one()
        assert candidate.resolution == classify.RESOLUTION_REVIEW
        assert _links(db_session, media) == [], (
            "le rattachement que le seuil ne justifie plus est retiré"
        )
        assert media.attachment_status == "pending_review"

    def test_lowering_the_high_threshold_attaches_a_previously_reviewed_candidate(
        self, db_session, owner, shooting, batch
    ):
        media = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="down"
        )
        add_candidate(db_session, media, number="12", score=0.65)

        classify.project_media(db_session, media, load_ocr_settings(db_session))
        db_session.commit()
        assert _links(db_session, media) == []

        write_ocr_settings(db_session, {OCR_HIGH_KEY: 0.60, OCR_LOW_KEY: 0.30}, updated_by=owner.id)
        db_session.commit()
        classify.project_media(db_session, media, load_ocr_settings(db_session))
        db_session.commit()
        db_session.refresh(media)

        assert len(_links(db_session, media)) == 1
        assert media.attachment_status == "engagement_attached"

    def test_the_raw_candidate_is_never_rewritten_by_a_threshold_change(
        self, db_session, owner, shooting, batch
    ):
        """Le texte lu et le score sont des **faits**. Seule leur interprétation bouge."""
        media = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="facts"
        )
        candidate = add_candidate(db_session, media, number="12", score=0.85, raw_text="I2")
        original = (candidate.raw_text, float(candidate.confidence), candidate.bbox)

        for high in (0.5, 0.9, 0.99):
            write_ocr_settings(db_session, {OCR_HIGH_KEY: high}, updated_by=owner.id)
            db_session.commit()
            classify.project_media(db_session, media, load_ocr_settings(db_session))
            db_session.commit()

        db_session.refresh(candidate)
        assert (candidate.raw_text, float(candidate.confidence), candidate.bbox) == original

    def test_a_human_decision_survives_every_threshold_change(
        self, db_session, owner, shooting, batch
    ):
        """L'arbitrage humain est terminal — c'est ce qui rend la file de validation utile."""
        media = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="human"
        )
        engagement = _engagement(db_session, shooting, "12")
        add_candidate(
            db_session,
            media,
            number="12",
            score=0.51,
            resolution=classify.RESOLUTION_ACCEPTED,
            engagement_id=engagement.id,
            resolved_by=owner.id,
        )

        for high, low in ((0.99, 0.95), (0.10, 0.05), (0.80, 0.45)):
            write_ocr_settings(
                db_session, {OCR_HIGH_KEY: high, OCR_LOW_KEY: low}, updated_by=owner.id
            )
            db_session.commit()
            classify.project_media(db_session, media, load_ocr_settings(db_session))
            db_session.commit()

            candidate = db_session.execute(
                select(MediaOcrCandidate).where(MediaOcrCandidate.media_id == media.id)
            ).scalar_one()
            assert candidate.resolution == classify.RESOLUTION_ACCEPTED
            [link] = _links(db_session, media)
            assert link.engagement_id == engagement.id
            assert link.created_by == owner.id, "qui a tranché reste tracé"

    def test_a_manual_attachment_is_never_undone_by_a_threshold_change(
        self, db_session, owner, shooting, batch
    ):
        media = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="manual"
        )
        engagement = _engagement(db_session, shooting, "250")
        db_session.add(
            MediaEngagement(
                media_id=media.id, engagement_id=engagement.id, source="human", created_by=owner.id
            )
        )
        # Un candidat OCR sans rapport, qui va être balayé par le relèvement du seuil.
        add_candidate(db_session, media, number="12", score=0.85)
        db_session.commit()

        classify.project_media(db_session, media, load_ocr_settings(db_session))
        db_session.commit()
        assert len(_links(db_session, media)) == 2

        write_ocr_settings(db_session, {OCR_HIGH_KEY: 0.99}, updated_by=owner.id)
        db_session.commit()
        classify.project_media(db_session, media, load_ocr_settings(db_session))
        db_session.commit()
        db_session.refresh(media)

        [link] = _links(db_session, media)
        assert link.source == "human"
        assert link.engagement_id == engagement.id
        assert media.attachment_status == "engagement_attached"
        assert media.attachment_source == "human"


class TestSimulationDeDistribution:
    def test_simulation_matches_what_the_projection_would_do(
        self, db_session, owner, shooting, batch
    ):
        """`PUT /settings/ocr` promet un aperçu : il doit être exact, pas indicatif."""
        for index, score in enumerate((0.95, 0.72, 0.30, 0.91)):
            media = make_media(
                db_session, owner=owner, batch=batch, shooting=shooting, key_suffix=f"sim{index}"
            )
            add_candidate(db_session, media, number="12", score=score)
        ghost = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="sim-ghost"
        )
        add_candidate(db_session, ghost, number="99", score=0.99)

        media_ids = [
            int(row)
            for row in db_session.execute(select(MediaOcrCandidate.media_id).distinct()).scalars()
        ]
        # Situation de production : les candidats ont déjà été projetés une fois par
        # `ocr_media` (qui insère et projette dans la même transaction). C'est cette
        # première projection qui pose `engagement_id`, dont la simulation a besoin.
        classify.project_media_batch(db_session, media_ids, load_ocr_settings(db_session))
        db_session.commit()

        preview = classify.simulate_distribution(db_session, high=0.90, low=0.50)

        write_ocr_settings(db_session, {OCR_HIGH_KEY: 0.90, OCR_LOW_KEY: 0.50}, updated_by=owner.id)
        db_session.commit()
        classify.project_media_batch(db_session, media_ids, load_ocr_settings(db_session))
        db_session.commit()

        actual = classify.current_distribution(db_session)
        assert (preview.auto, preview.review, preview.abstain, preview.not_engaged) == (
            actual.auto,
            actual.review,
            actual.abstain,
            actual.not_engaged,
        )
        assert actual.not_engaged == 1, "le n°99 reste une incohérence quel que soit le seuil"
