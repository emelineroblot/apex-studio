"""Générateur de jeu de démo (§3-N.1 du plan, Décision N) — déterminisme, idempotence,
probité (`is_simulated`), forme des distributions.

Les tests de **déterminisme** tournent sur un volume réduit (`SHOOTING_COUNT`/
`TARGET_SIMULATED_MEDIA` patchés) — la reproductibilité bit-à-bit ne dépend pas de
l'échelle, et deux resets à ~8000 médias coûteraient une bonne partie du budget de la suite
par défaut pour rien. Le volume réel (~8000) est vérifié une seule fois, dans
`test_full_volume_matches_the_plan_targets`, et **partagé** avec
`tests/search/test_perf.py` par un seed en amont commun (voir docstring de ce fichier).
"""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apex.demo import seed as seed_module
from apex.models.catalog import Client, Driver
from apex.models.media import Media
from apex.models.shooting import Engagement, Shooting


def _fingerprint(session: Session) -> str:
    """Empreinte des champs **déterministes** (§3-N.2 : « hash trié des lignes clés »).

    Exclut délibérément `created_at`/`updated_at` (horodatage réel de l'insertion, jamais
    reproductible d'un run à l'autre) — tout le reste doit être identique, graine fixe.
    """
    media_rows = session.execute(
        select(
            Media.camera_id,
            Media.iso,
            Media.focal_length,
            Media.attachment_status,
            Media.attachment_source,
            Media.shot_at,
            Media.caption,
            Media.is_series_representative,
        )
    ).all()
    engagement_rows = session.execute(
        select(
            Engagement.shooting_id, Engagement.car_number, Engagement.driver_id, Engagement.team_id
        )
    ).all()
    shooting_rows = session.execute(select(Shooting.title, Shooting.starts_at)).all()

    canonical = (
        repr(sorted(map(str, media_rows)))
        + repr(sorted(map(str, engagement_rows)))
        + repr(sorted(map(str, shooting_rows)))
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@pytest.fixture
def small_seed(monkeypatch: pytest.MonkeyPatch):
    """Patch le volume pour un test de déterminisme rapide (§ docstring de module)."""
    monkeypatch.setattr(seed_module, "SHOOTING_COUNT", 3)
    monkeypatch.setattr(seed_module, "TARGET_SIMULATED_MEDIA", 180)
    yield


class TestDeterminism:
    def test_two_resets_produce_bit_for_bit_identical_business_data(
        self, db_session: Session, small_seed
    ) -> None:
        seed_module.run_seed(db_session, reset=True)
        db_session.commit()
        first = _fingerprint(db_session)

        seed_module.run_seed(db_session, reset=True)
        db_session.commit()
        second = _fingerprint(db_session)

        assert first == second

    def test_reset_false_on_an_empty_database_seeds_once(
        self, db_session: Session, small_seed
    ) -> None:
        result = seed_module.run_seed(db_session, reset=False)
        db_session.commit()
        assert result.ran is True
        assert result.shootings == 3

    def test_reset_false_on_an_already_seeded_database_is_a_no_op(
        self, db_session: Session, small_seed
    ) -> None:
        seed_module.run_seed(db_session, reset=True)
        db_session.commit()
        before = _fingerprint(db_session)

        result = seed_module.run_seed(db_session, reset=False)
        db_session.commit()

        assert result.ran is False
        assert _fingerprint(db_session) == before


class TestProbity:
    def test_every_generated_media_is_flagged_simulated(
        self, db_session: Session, small_seed
    ) -> None:
        seed_module.run_seed(db_session, reset=True)
        db_session.commit()

        total = db_session.execute(select(func.count()).select_from(Media)).scalar_one()
        simulated = db_session.execute(
            select(func.count()).select_from(Media).where(Media.is_simulated.is_(True))
        ).scalar_one()
        assert total > 0
        assert total == simulated  # aucune photo réelle dans ce test (demo-photos/ absent)

    def test_the_real_prerequisite_is_reported_but_never_fails_the_seed(
        self, db_session: Session, small_seed
    ) -> None:
        result = seed_module.run_seed(db_session, reset=True)
        db_session.commit()
        assert result.real_media == 0
        assert result.real_photos_skipped_reason is not None


class TestFullVolumeMatchesThePlanTargets:
    def test_full_volume_matches_the_plan_targets(self, db_session: Session) -> None:
        """Volume réel (~8000, §3-N.1) — payé une seule fois dans toute la suite."""
        result = seed_module.run_seed(db_session, reset=True)
        db_session.commit()

        assert result.shootings == 15
        assert result.clients == 10
        assert result.drivers == 40
        assert result.cameras == 6
        # « ~8000 » : tolérance généreuse, la volumétrie par shooting est tirée (§3-N.1).
        assert 6500 <= result.simulated_media <= 9500

        total_clients = db_session.execute(select(func.count()).select_from(Client)).scalar_one()
        total_drivers = db_session.execute(select(func.count()).select_from(Driver)).scalar_one()
        assert total_clients == 10
        assert total_drivers == 40

        # Distribution défendable (§3-N.1) : engagement_attached largement majoritaire,
        # quarantaine minoritaire — tolérances larges (générateur stochastique).
        counts = result.attachment_status_counts
        total = result.simulated_media
        assert counts.get("engagement_attached", 0) / total > 0.65
        assert counts.get("quarantined", 0) / total < 0.05
