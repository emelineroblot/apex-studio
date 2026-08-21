"""API J2 : file de validation, réglages des seuils, taux de rattachement automatique.

Trois surfaces, une même idée : **l'IA propose, l'humain arbitre, et tout est traçable.**
"""

from __future__ import annotations

from sqlalchemy import select

from apex.models.media import MediaEngagement
from apex.models.search import MediaOcrCandidate
from apex.models.shooting import Engagement, Shooting, ShootingStaff
from apex.pipeline.ocr import classify
from apex.services.ocr_settings import (
    OCR_HIGH_DEFAULT,
    OCR_HIGH_KEY,
    OCR_LOW_DEFAULT,
    OCR_LOW_KEY,
    load_ocr_settings,
    write_ocr_settings,
)
from tests.conftest import auth_headers, make_user
from tests.ocr.conftest import add_candidate, make_media

API = "/api/v1"


def _engagement(db, shooting: Shooting, car_number: str) -> Engagement:
    return db.execute(
        select(Engagement).where(
            Engagement.shooting_id == shooting.id, Engagement.car_number == car_number
        )
    ).scalar_one()


def _project(db, medias):
    classify.project_media_batch(db, [media.id for media in medias], load_ocr_settings(db))
    db.commit()


class TestFileDeValidation:
    def test_the_queue_exposes_the_reading_its_score_and_the_business_context(
        self, client, db_session, owner, shooting, batch
    ):
        """L'écran de validation montre ce que le modèle a lu **et** ce que ça veut dire."""
        media = make_media(db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="q1")
        add_candidate(db_session, media, number="12", score=0.62, raw_text="I2")
        _project(db_session, [media])

        response = client.get(f"{API}/review/queue", headers=auth_headers(owner))
        assert response.status_code == 200, response.text
        payload = response.json()

        assert payload["remaining"] == 1
        [item] = payload["items"]
        assert item["raw_text"] == "I2", "le texte brut du modèle reste visible"
        assert item["normalized_number"] == "12"
        assert item["confidence"] == 0.62
        assert item["bbox"]["w"] > 0
        # La jointure métier : le numéro seul ne dit rien, le contexte fait tout.
        assert item["suggested_engagement"]["car_number"] == "12"
        assert item["suggested_engagement"]["driver"] == "Camille Roux"
        assert item["suggested_engagement"]["client"] == "Écurie Chicane"
        assert {alt["car_number"] for alt in item["other_engagements"]} == {"07", "250"}

    def test_an_inconsistency_never_reaches_the_review_queue(
        self, client, db_session, owner, shooting, batch
    ):
        """Un numéro hors plateau n'est pas « à valider » : accepter n'y voudrait rien dire."""
        media = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="ghost"
        )
        add_candidate(db_session, media, number="99", score=0.60)
        _project(db_session, [media])

        payload = client.get(f"{API}/review/queue", headers=auth_headers(owner)).json()
        assert payload["items"] == []
        assert payload["remaining"] == 0

    def test_a_photographer_only_sees_his_own_queue(
        self, client, db_session, owner, shooting, batch
    ):
        photographer = make_user(db_session, role="photographer", email="photo-ocr@apex-test.dev")
        media = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="cloison"
        )
        add_candidate(db_session, media, number="12", score=0.62)
        _project(db_session, [media])

        payload = client.get(f"{API}/review/queue", headers=auth_headers(photographer)).json()
        assert payload["items"] == [], "non affecté au shooting : rien à voir"

        db_session.add(
            ShootingStaff(shooting_id=shooting.id, user_id=photographer.id, role="photographer")
        )
        db_session.commit()
        payload = client.get(f"{API}/review/queue", headers=auth_headers(photographer)).json()
        assert len(payload["items"]) == 1

    def test_decisions_are_applied_in_batch_with_per_line_errors(
        self, client, db_session, owner, shooting, batch
    ):
        """Une ligne fautive ne fait pas échouer le lot — l'écran se traite au clavier, en rafale."""
        accepted = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="acc"
        )
        rejected = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="rej"
        )
        reassigned = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="rea"
        )
        candidates = [
            add_candidate(db_session, accepted, number="12", score=0.62),
            add_candidate(db_session, rejected, number="12", score=0.55),
            add_candidate(db_session, reassigned, number="12", score=0.50),
        ]
        _project(db_session, [accepted, rejected, reassigned])

        response = client.post(
            f"{API}/review/decisions",
            headers=auth_headers(owner),
            json={
                "decisions": [
                    {"candidate_id": candidates[0].id, "action": "accept"},
                    {"candidate_id": candidates[1].id, "action": "reject"},
                    {
                        "candidate_id": candidates[2].id,
                        "action": "reassign",
                        "engagement_id": _engagement(db_session, shooting, "250").id,
                    },
                    {"candidate_id": 999_999, "action": "accept"},
                ]
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["applied"] == 3
        assert payload["skipped"] == 1
        assert payload["errors"][0]["candidate_id"] == 999_999
        assert payload["remaining"] == 0

        db_session.expire_all()
        # Accepté → rattaché, avec la trace de qui a tranché.
        [link] = _links(db_session, accepted)
        assert link.engagement_id == _engagement(db_session, shooting, "12").id
        assert link.created_by == owner.id
        db_session.refresh(accepted)
        assert accepted.attachment_status == "engagement_attached"
        assert accepted.attachment_source == "human"

        # Rejeté → aucun rattachement, et le média retombe où il était.
        assert _links(db_session, rejected) == []
        db_session.refresh(rejected)
        assert rejected.attachment_status == "shooting_attached"

        # Réaffecté → rattaché à l'engagement choisi par l'humain, pas à celui suggéré.
        [link] = _links(db_session, reassigned)
        assert link.engagement_id == _engagement(db_session, shooting, "250").id

    def test_a_candidate_cannot_be_arbitrated_twice(
        self, client, db_session, owner, shooting, batch
    ):
        media = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="twice"
        )
        candidate = add_candidate(db_session, media, number="12", score=0.62)
        _project(db_session, [media])

        body = {"decisions": [{"candidate_id": candidate.id, "action": "accept"}]}
        assert (
            client.post(f"{API}/review/decisions", headers=auth_headers(owner), json=body).json()[
                "applied"
            ]
            == 1
        )
        second = client.post(
            f"{API}/review/decisions", headers=auth_headers(owner), json=body
        ).json()
        assert second["applied"] == 0
        assert "déjà été arbitré" in second["errors"][0]["message"]

    def test_reassignment_refuses_an_engagement_from_another_event(
        self, client, db_session, owner, shooting, batch
    ):
        """Le n°12 de ce week-end n'est pas le n°12 du suivant — invariant métier."""
        other = Shooting(
            circuit_id=shooting.circuit_id,
            title="Un autre meeting",
            starts_at=shooting.starts_at,
            ends_at=shooting.ends_at,
        )
        db_session.add(other)
        db_session.flush()
        foreign = Engagement(shooting_id=other.id, car_number="12")
        db_session.add(foreign)
        db_session.commit()

        media = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="foreign"
        )
        candidate = add_candidate(db_session, media, number="12", score=0.62)
        _project(db_session, [media])

        payload = client.post(
            f"{API}/review/decisions",
            headers=auth_headers(owner),
            json={
                "decisions": [
                    {
                        "candidate_id": candidate.id,
                        "action": "reassign",
                        "engagement_id": foreign.id,
                    }
                ]
            },
        ).json()
        assert payload["applied"] == 0
        assert "Engagement inconnu" in payload["errors"][0]["message"]
        assert _links(db_session, media) == []


class TestReglagesDesSeuils:
    def test_reading_the_thresholds_returns_the_current_distribution(
        self, client, db_session, owner, shooting, batch
    ):
        for index, score in enumerate((0.95, 0.60, 0.20)):
            media = make_media(
                db_session, owner=owner, batch=batch, shooting=shooting, key_suffix=f"d{index}"
            )
            add_candidate(db_session, media, number="12", score=score)
        ghost = make_media(db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="dg")
        add_candidate(db_session, ghost, number="99", score=0.99)
        classify.project_media_batch(
            db_session,
            [
                int(row)
                for row in db_session.execute(
                    select(MediaOcrCandidate.media_id).distinct()
                ).scalars()
            ],
            load_ocr_settings(db_session),
        )
        db_session.commit()

        payload = client.get(f"{API}/settings/ocr", headers=auth_headers(owner)).json()
        assert payload["high"] == OCR_HIGH_DEFAULT
        assert payload["low"] == OCR_LOW_DEFAULT
        assert payload["distribution"] == {"auto": 1, "review": 1, "abstain": 1, "not_engaged": 1}

    def test_only_the_owner_can_change_the_thresholds(self, client, db_session, shooting):
        photographer = make_user(db_session, role="photographer", email="photo-set@apex-test.dev")
        response = client.put(
            f"{API}/settings/ocr",
            headers=auth_headers(photographer),
            json={"high": 0.9, "low": 0.4},
        )
        assert response.status_code == 403

    def test_inverted_thresholds_are_refused_rather_than_silently_fixed(
        self, client, db_session, owner
    ):
        response = client.put(
            f"{API}/settings/ocr", headers=auth_headers(owner), json={"high": 0.3, "low": 0.9}
        )
        assert response.status_code == 422
        assert "seuil bas" in str(response.json()["detail"])

    def test_changing_the_thresholds_previews_then_redistributes(
        self, client, db_session, owner, shooting, batch
    ):
        """Le critère d'acceptation, vu depuis l'API : simulation, écriture, redistribution."""
        medias = []
        for index, score in enumerate((0.95, 0.85, 0.60, 0.20)):
            media = make_media(
                db_session, owner=owner, batch=batch, shooting=shooting, key_suffix=f"r{index}"
            )
            add_candidate(db_session, media, number="12", score=score)
            medias.append(media)
        _project(db_session, medias)
        assert _attached(db_session) == 2

        response = client.put(
            f"{API}/settings/ocr", headers=auth_headers(owner), json={"high": 0.90, "low": 0.45}
        )
        assert response.status_code == 200, response.text
        payload = response.json()

        # La simulation est annoncée avant application, et elle est exacte.
        assert payload["preview_distribution"] == {"auto": 1, "review": 2, "abstain": 1}
        assert payload["settings"]["high"] == 0.90
        assert payload["reclassify_job_id"] > 0
        assert payload["settings"]["distribution"]["auto"] == 1

        db_session.expire_all()
        assert _attached(db_session) == 1, (
            "le rattachement que le seuil ne justifie plus est retiré"
        )

    def test_lowering_the_thresholds_puts_the_attachments_back(
        self, client, db_session, owner, shooting, batch
    ):
        medias = []
        for index, score in enumerate((0.95, 0.85, 0.60)):
            media = make_media(
                db_session, owner=owner, batch=batch, shooting=shooting, key_suffix=f"b{index}"
            )
            add_candidate(db_session, media, number="12", score=score)
            medias.append(media)
        write_ocr_settings(db_session, {OCR_HIGH_KEY: 0.99, OCR_LOW_KEY: 0.45}, updated_by=owner.id)
        db_session.commit()
        _project(db_session, medias)
        assert _attached(db_session) == 0

        client.put(
            f"{API}/settings/ocr", headers=auth_headers(owner), json={"high": 0.50, "low": 0.10}
        )
        db_session.expire_all()
        assert _attached(db_session) == 3


class TestTauxDeRattachementAutomatique:
    def test_the_rate_counts_only_what_the_machine_did_alone(
        self, client, db_session, owner, shooting, batch
    ):
        """Une validation humaine ne gonfle pas le taux — c'est tout l'intérêt de le publier."""
        auto = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="s-auto"
        )
        add_candidate(db_session, auto, number="12", score=0.95)

        validated = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="s-val"
        )
        add_candidate(
            db_session,
            validated,
            number="250",
            score=0.60,
            resolution=classify.RESOLUTION_ACCEPTED,
            engagement_id=_engagement(db_session, shooting, "250").id,
            resolved_by=owner.id,
        )

        time_only = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="s-time"
        )
        orphan = make_media(
            db_session, owner=owner, batch=batch, shooting=None, key_suffix="s-orphan"
        )
        _project(db_session, [auto, validated, time_only, orphan])

        payload = client.get(f"{API}/stats/auto-attach-rate", headers=auth_headers(owner)).json()
        assert payload["total"] == 4
        assert payload["auto_ocr"] == 1
        assert payload["human"] == 1
        assert payload["auto_time"] == 1
        assert payload["unattached"] == 1
        assert payload["rate"] == 0.5

    def test_the_rate_can_be_scoped_to_a_shooting(self, client, db_session, owner, shooting, batch):
        media = make_media(db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="sc")
        add_candidate(db_session, media, number="12", score=0.95)
        _project(db_session, [media])

        payload = client.get(
            f"{API}/stats/auto-attach-rate?shooting_id={shooting.id}", headers=auth_headers(owner)
        ).json()
        assert payload["total"] == 1
        assert payload["rate"] == 1.0

    def test_an_empty_scope_reports_zero_rather_than_dividing_by_zero(
        self, client, db_session, owner
    ):
        payload = client.get(f"{API}/stats/auto-attach-rate", headers=auth_headers(owner)).json()
        assert payload == {
            "total": 0,
            "auto_time": 0,
            "auto_ocr": 0,
            "human": 0,
            "unattached": 0,
            "rate": 0.0,
        }


class TestCandidatsEtRattachementManuel:
    def test_the_raw_candidates_are_exposed_for_the_ui(
        self, client, db_session, owner, shooting, batch
    ):
        media = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="raw"
        )
        add_candidate(db_session, media, number="12", score=0.95, raw_text="I2")
        _project(db_session, [media])

        payload = client.get(f"{API}/media/{media.id}/ocr", headers=auth_headers(owner)).json()
        [candidate] = payload["candidates"]
        assert candidate["raw_text"] == "I2"
        assert candidate["normalized_number"] == "12"
        assert candidate["confidence"] == 0.95
        assert candidate["resolution"] == "auto"
        assert candidate["engagement_id"] is not None

    def test_a_manual_attachment_is_traced_as_human(
        self, client, db_session, owner, shooting, batch
    ):
        media = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="man"
        )
        engagement = _engagement(db_session, shooting, "07")

        response = client.post(
            f"{API}/media/{media.id}/engagements",
            headers=auth_headers(owner),
            json={"engagement_id": engagement.id},
        )
        assert response.status_code == 201, response.text
        assert response.json()["source"] == "human"

        db_session.expire_all()
        [link] = _links(db_session, media)
        assert link.source == "human"
        assert link.created_by == owner.id

    def test_two_manual_attachments_can_coexist_on_one_photo(
        self, client, db_session, owner, shooting, batch
    ):
        media = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="man2"
        )
        for car_number in ("12", "250"):
            response = client.post(
                f"{API}/media/{media.id}/engagements",
                headers=auth_headers(owner),
                json={"engagement_id": _engagement(db_session, shooting, car_number).id},
            )
            assert response.status_code == 201
        db_session.expire_all()
        assert len(_links(db_session, media)) == 2

    def test_removing_the_last_attachment_returns_the_media_to_its_shooting(
        self, client, db_session, owner, shooting, batch
    ):
        media = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="del"
        )
        engagement = _engagement(db_session, shooting, "12")
        client.post(
            f"{API}/media/{media.id}/engagements",
            headers=auth_headers(owner),
            json={"engagement_id": engagement.id},
        )
        response = client.delete(
            f"{API}/media/{media.id}/engagements/{engagement.id}", headers=auth_headers(owner)
        )
        assert response.status_code == 204

        db_session.expire_all()
        db_session.refresh(media)
        assert _links(db_session, media) == []
        assert media.attachment_status == "shooting_attached"


def _links(db, media):
    return list(
        db.execute(
            select(MediaEngagement)
            .where(MediaEngagement.media_id == media.id)
            .order_by(MediaEngagement.engagement_id)
        ).scalars()
    )


def _attached(db) -> int:
    db.expire_all()
    return len(list(db.execute(select(MediaEngagement)).scalars()))
