"""`reclassify_ocr` — **changer un seuil ne relance jamais l'inférence**.

C'est le point de design central du jalon (§3-J.4). Deux preuves, pas une affirmation :

1. un moteur qui **explose** dès qu'on le lit est injecté pendant toute la re-projection ;
2. le module `reclassify_ocr` est inspecté : il n'importe pas `engine.py`, ni directement,
   ni transitivement par `classify.py`.

La seconde preuve est structurelle. Sans elle, un futur refactor pourrait réintroduire une
inférence dans le chemin de re-projection sans qu'aucun test ne s'en aperçoive — la première
preuve ne couvre que les médias effectivement traités par ce test.
"""

from __future__ import annotations

import ast
from pathlib import Path

from sqlalchemy import select

from apex.db import SessionLocal
from apex.models.job import Job
from apex.models.media import MediaEngagement
from apex.models.search import MediaOcrCandidate
from apex.pipeline.ocr import classify
from apex.pipeline.ocr.engine import set_engine
from apex.queue.enqueue import enqueue
from apex.queue.runner import drain
from apex.services.ocr_settings import OCR_HIGH_KEY, OCR_LOW_KEY, write_ocr_settings
from tests.ocr.conftest import ExplodingOcrEngine, add_candidate, make_media


def _run_queue() -> None:
    drain(SessionLocal, "test-reclassify", deadline=None, batch_size=10)


class TestReprojectionSansInference:
    def test_a_threshold_change_redistributes_without_calling_the_model(
        self, db_session, owner, shooting, batch
    ):
        """Le critère d'acceptation, prouvé par un moteur qui refuse de lire."""
        medias = []
        for index, score in enumerate((0.95, 0.83, 0.60, 0.25)):
            media = make_media(
                db_session, owner=owner, batch=batch, shooting=shooting, key_suffix=f"rc{index}"
            )
            add_candidate(db_session, media, number="12", score=score)
            medias.append(media)

        write_ocr_settings(db_session, {OCR_HIGH_KEY: 0.80, OCR_LOW_KEY: 0.45}, updated_by=owner.id)
        enqueue(db_session, "reclassify_ocr", {}, dedupe_key="reclassify", priority=80)
        db_session.commit()

        set_engine(ExplodingOcrEngine())  # toute inférence ferait échouer le job
        _run_queue()

        resolutions = _resolutions(db_session)
        assert resolutions == [
            classify.RESOLUTION_AUTO,
            classify.RESOLUTION_AUTO,
            classify.RESOLUTION_REVIEW,
            classify.RESOLUTION_ABSTAIN,
        ]
        assert _attached_count(db_session) == 2

        # On relève le seuil haut : la redistribution doit être immédiate et sans inférence.
        write_ocr_settings(db_session, {OCR_HIGH_KEY: 0.90}, updated_by=owner.id)
        enqueue(db_session, "reclassify_ocr", {}, dedupe_key="reclassify", priority=80)
        db_session.commit()
        _run_queue()

        assert _resolutions(db_session) == [
            classify.RESOLUTION_AUTO,
            classify.RESOLUTION_REVIEW,
            classify.RESOLUTION_REVIEW,
            classify.RESOLUTION_ABSTAIN,
        ]
        assert _attached_count(db_session) == 1

        job = db_session.execute(
            select(Job).where(Job.kind == "reclassify_ocr").order_by(Job.id.desc()).limit(1)
        ).scalar_one()
        assert job.status == "done"
        assert job.result["inference_runs"] == 0
        assert job.result["media_touched"] == len(medias)

    def test_the_reclassify_path_does_not_import_the_engine(self) -> None:
        """Preuve structurelle : aucun chemin d'import ne mène au moteur.

        Un test de comportement ne couvre que les cas qu'il exécute ; celui-ci ferme la
        porte pour de bon. Si un futur refactor réintroduit `engine` dans la chaîne de
        re-projection, il échoue immédiatement et explique pourquoi.
        """
        root = Path(__file__).resolve().parents[2] / "src" / "apex"
        checked = [
            root / "queue" / "handlers" / "reclassify_ocr.py",
            root / "pipeline" / "ocr" / "classify.py",
            root / "pipeline" / "ocr" / "normalize.py",
            root / "services" / "ocr_settings.py",
        ]
        for path in checked:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
                    imported.update(f"{node.module}.{alias.name}" for alias in node.names)
            offending = {name for name in imported if "ocr.engine" in name}
            assert not offending, (
                f"{path.name} importe {offending} : la re-projection des candidats doit être "
                "structurellement incapable de déclencher une inférence."
            )

    def test_reclassification_can_be_scoped_to_a_single_shooting(
        self, db_session, owner, shooting, batch
    ):
        media = make_media(
            db_session, owner=owner, batch=batch, shooting=shooting, key_suffix="scoped"
        )
        add_candidate(db_session, media, number="12", score=0.95)
        orphan = make_media(db_session, owner=owner, batch=batch, shooting=None, key_suffix="out")
        add_candidate(db_session, orphan, number="12", score=0.95)

        enqueue(
            db_session,
            "reclassify_ocr",
            {"shooting_id": shooting.id},
            dedupe_key="reclassify",
            priority=80,
        )
        db_session.commit()
        set_engine(ExplodingOcrEngine())
        _run_queue()

        job = db_session.execute(
            select(Job).where(Job.kind == "reclassify_ocr").order_by(Job.id.desc()).limit(1)
        ).scalar_one()
        assert job.status == "done"
        assert job.result["media_touched"] == 1


def _resolutions(db_session) -> list[str]:
    db_session.expire_all()
    return list(
        db_session.execute(
            select(MediaOcrCandidate.resolution).order_by(MediaOcrCandidate.id)
        ).scalars()
    )


def _attached_count(db_session) -> int:
    db_session.expire_all()
    return len(list(db_session.execute(select(MediaEngagement)).scalars()))
