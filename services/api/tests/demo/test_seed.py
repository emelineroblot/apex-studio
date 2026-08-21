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
from apex.models.media import Media, MediaEngagement
from apex.models.shooting import Engagement, Shooting
from apex.models.user import AppUser
from apex.pipeline.ocr import classify
from tests.conftest import auth_headers

API = "/api/v1"


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
def small_seed(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Patch le volume pour un test de déterminisme rapide (§ docstring de module).

    Isole aussi `real_photos_dir` sur un répertoire vide (§ sourcing des photos réelles,
    `.agent-team/implementation.md`, Backend) : `settings.real_photos_dir` par défaut
    (`./demo-photos`) résout, quand `pytest` tourne depuis `services/api`, vers **le même
    dossier** que celui peuplé par `scripts/source_demo_photos.py`. Sans cette isolation,
    ces tests de déterminisme/probité ingéreraient les ~300 photos réelles à chaque appel
    — lent, et surtout faux pour `TestProbity` (`total == simulated` ne tiendrait plus).
    Les tests qui veulent vraiment des photos réelles écrasent ce chemin explicitement
    après coup (§ `TestRealPhotosAreReassignedToADemoShootingWhenTheirGenuineExifMisses`).
    """
    monkeypatch.setattr(seed_module, "SHOOTING_COUNT", 3)
    monkeypatch.setattr(seed_module, "TARGET_SIMULATED_MEDIA", 180)
    monkeypatch.setattr(seed_module.settings, "real_photos_dir", str(tmp_path / "no-real-photos"))
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


class TestPartialCatalogSecondSafetyNet:
    def test_reset_false_on_a_partial_catalog_refuses_instead_of_a_silent_no_op(
        self, db_session: Session, small_seed
    ) -> None:
        """Second filet du correctif heartbeat (revue J2, 🔴 n°2).

        Simule l'état laissé par un `POST /demo/seed` interrompu **avant** le commit final
        de `run_seed` (peu importe la cause exacte de l'interruption) : `client` peuplé,
        `last_demo_reset` jamais écrit. Sans ce filet, `run_seed(reset=False)` rejoué
        verrait `catalog_exists=True` et renverrait silencieusement `ran=False` — la démo
        resterait cassée en permanence, sans qu'aucune erreur ne le signale.
        """
        db_session.add(Client(name="Catalogue interrompu", kind="team"))
        db_session.commit()

        with pytest.raises(seed_module.PartialDemoCatalogError):
            seed_module.run_seed(db_session, reset=False)

    def test_reset_true_repairs_a_partial_catalog(self, db_session: Session, small_seed) -> None:
        """`reset=True` truque et régénère toujours — un catalogue partiel n'est jamais un
        obstacle à la réparation explicite, seul le repli silencieux (`reset=False`) l'est.
        """
        db_session.add(Client(name="Catalogue interrompu", kind="team"))
        db_session.commit()

        result = seed_module.run_seed(db_session, reset=True)
        db_session.commit()
        assert result.ran is True
        assert result.reset is True


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


class TestRealPhotosAreReassignedToADemoShootingWhenTheirGenuineExifMisses:
    """§ `.agent-team/implementation.md` (Backend, sourcing des photos réelles).

    Une photo réelle porte une date de prise de vue authentique (parfois des années avant
    que le jeu de démo n'existe) — elle ne recoupe donc quasiment jamais la fenêtre d'un
    shooting généré relativement à « maintenant ». Sans le correctif round-robin de
    `_ingest_real_photos`, ces photos resteraient perpétuellement dans le bac « à
    rattacher » et l'OCR ne les lirait jamais (`ocr_media` ignore `shooting_id is None`).
    """

    def test_a_real_photo_with_an_old_exif_date_still_gets_attached_and_queued_for_ocr(
        self, db_session: Session, small_seed, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tests.support.images import make_valid_jpeg

        real_dir = tmp_path / "demo-photos"
        real_dir.mkdir()
        # Date authentique très antérieure à toute fenêtre de shooting générée
        # (`_create_shootings` : les 120 derniers jours autour de « maintenant »).
        (real_dir / "0000_old_race.jpg").write_bytes(
            make_valid_jpeg(shot_at="2015:06:14 10:30:00", serial="REAL001")
        )
        monkeypatch.setattr(seed_module.settings, "real_photos_dir", str(real_dir))

        result = seed_module.run_seed(db_session, reset=True)
        db_session.commit()

        assert result.real_media == 1
        media = db_session.execute(select(Media).where(Media.is_simulated.is_(False))).scalar_one()
        # La date authentique est préservée telle quelle...
        assert media.shot_at_exif is not None
        assert media.shot_at_exif.year == 2015
        # ...mais l'opérationnelle (`shot_at`) a été replacée dans un shooting du jeu pour
        # que le reste du pipeline (OCR, engagements) soit démontrable.
        assert media.shooting_id is not None
        assert media.attachment_status == "shooting_attached"
        assert media.attachment_source == "pipeline_time"

        from apex.models.job import Job

        ocr_jobs = db_session.execute(select(Job).where(Job.kind == "ocr_media")).scalars().all()
        assert any(job.payload.get("media_id") == media.id for job in ocr_jobs)
        assert all(job.status == "pending" for job in ocr_jobs)


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

        # Revue J2 (🟠 n°9) : le jeu de démo doit démontrer le curseur de seuils sur tout le
        # catalogue, pas sur 5,6 % — reproduit la contradiction chiffrée de la revue
        # (`auto: 0` vs `auto_ocr: ...`) et montre qu'elle a disparu.
        distribution = classify.current_distribution(db_session)
        assert distribution.auto > 0, "GET /settings/ocr afficherait encore « auto: 0 »"
        # Presque tout le bac `engagement_attached`/pipeline_ocr (~72 %) doit désormais
        # porter un candidat `auto` — tolérance large (tirage stochastique, cf. §3-N.1).
        assert distribution.auto / counts.get("engagement_attached", 1) > 0.5
        assert distribution.abstain > 0, "aucun candidat sous le seuil bas : rien à redistribuer"


class TestPendingReviewNeverMaterialisesAnEngagementAtSeedTime:
    """Intégration live J2 finale : `GET /stats/auto-attach-rate.auto_ocr` (`4875 → 4697`,
    -178) divergeait de `GET /settings/ocr.distribution.auto` et de la facette `/search`
    `status=engagement_attached` (toutes deux `4461 → 4697`, +236) après une baisse du
    seuil haut — alors qu'un seuil plus permissif ne peut que créer des rattachements.

    Cause racine : `_create_simulated_media` posait une ligne `media_engagement` pour
    **tout** média du bac `pending_review` (`group_engagement_ids` est peuplé pour ce bac
    aussi, § `_plan_shooting_media`, pour connaître l'engagement visé par son candidat OCR),
    alors que ce bac n'a — par construction — encore aucun rattachement matérialisé : seules
    `auto`/`accepted` (`classify.ATTACHING_RESOLUTIONS`) en créent un en production
    (`classify._materialise_links`). `auto_attach_rate.auto_ocr` compte par `EXISTS
    media_engagement` (média), tandis que `distribution.auto` compte des candidats
    `resolution='auto'` : le premier était donc gonflé de la taille de la file de
    validation, jusqu'à ce qu'une première projection (`PUT /settings/ocr`, `POST
    /jobs/tick`) retire ces liens fantômes — donnant l'illusion d'un recul.
    """

    def test_a_freshly_seeded_pending_review_media_has_no_media_engagement(
        self, db_session: Session, small_seed
    ) -> None:
        seed_module.run_seed(db_session, reset=True)
        db_session.commit()

        pending_review_ids = {
            int(row)
            for row in db_session.execute(
                select(Media.id).where(Media.attachment_status == "pending_review")
            ).scalars()
        }
        assert pending_review_ids, "le jeu de démo doit produire des médias en file de validation"

        phantom_ids = {
            int(row)
            for row in db_session.execute(
                select(MediaEngagement.media_id).where(
                    MediaEngagement.media_id.in_(pending_review_ids)
                )
            ).scalars()
        }
        assert not phantom_ids, (
            "un média `pending_review` porte déjà un `media_engagement` au sortir du seed — "
            "c'est ce qui gonflait artificiellement `auto_ocr` avant la première projection"
        )


class TestAutoAttachIndicatorsAgreeAfterLoweringTheThreshold:
    """Verrou de non-régression, cross-endpoints (même esprit que
    `tests/search/test_media_search_agreement.py`) : `GET /settings/ocr`, `GET
    /stats/auto-attach-rate` et `GET /search` doivent raconter la même histoire après une
    baisse du seuil haut. Une baisse de seuil ne peut que **créer** des rattachements
    automatiques — aucun des trois indicateurs ne doit donc jamais reculer.
    """

    def test_lowering_the_high_threshold_never_decreases_any_auto_attach_indicator(
        self, client, db_session: Session, small_seed
    ) -> None:
        seed_module.run_seed(db_session, reset=True)
        db_session.commit()
        owner = db_session.execute(select(AppUser).where(AppUser.role == "owner")).scalar_one()
        headers = auth_headers(owner)

        def _snapshot() -> tuple[int, int, int]:
            settings_payload = client.get(f"{API}/settings/ocr", headers=headers).json()
            stats_payload = client.get(f"{API}/stats/auto-attach-rate", headers=headers).json()
            search_payload = client.get(
                f"{API}/search",
                params={"series": "all", "status": ["engagement_attached"], "limit": 1},
                headers=headers,
            ).json()
            return (
                settings_payload["distribution"]["auto"],
                stats_payload["auto_ocr"],
                search_payload["total"],
            )

        before_distribution_auto, before_auto_ocr, before_attached = _snapshot()

        response = client.put(
            f"{API}/settings/ocr", headers=headers, json={"high": 0.60, "low": 0.45}
        )
        assert response.status_code == 200, response.text

        after_distribution_auto, after_auto_ocr, after_attached = _snapshot()

        # La baisse doit effectivement redistribuer quelque chose — sinon le test ne
        # vérifie rien (§3-N.1, candidats `pending_review` du jeu de démo à score
        # 0,46-0,79, au moins une partie franchit 0,60).
        assert after_distribution_auto > before_distribution_auto

        assert after_distribution_auto >= before_distribution_auto
        assert after_auto_ocr >= before_auto_ocr, (
            "auto_ocr a reculé après une baisse du seuil haut — deux écrans du produit se "
            "contrediraient devant un prospect (intégration live J2 finale)"
        )
        assert after_attached >= before_attached
