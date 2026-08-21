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


def _imported_apex_modules(path: Path) -> set[str]:
    """Modules `apex.*` référencés par `path`, imports imbriqués (fonctions, `TYPE_CHECKING`)
    inclus — `ast.walk` descend dans tout le corps du fichier, pas seulement le niveau module.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names if alias.name.startswith("apex"))
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("apex"):
            modules.add(node.module)
            # `from apex.pipeline.ocr import classify` importe potentiellement un
            # **sous-module** (`apex.pipeline.ocr.classify`) autant qu'un simple nom — les
            # deux candidats sont ajoutés, `_module_to_path` élimine ceux qui ne
            # correspondent à aucun fichier réel.
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def _module_to_path(root: Path, module: str) -> Path | None:
    """`apex.pipeline.ocr.classify` → `<root>/pipeline/ocr/classify.py` (`root` = `src/apex`).

    `None` si `module` ne correspond à aucun fichier réel (ex. une classe importée, pas un
    sous-module — cas normal, pas une erreur).
    """
    parts = module.split(".")[1:]  # retire le préfixe `apex` commun à `root`
    if not parts:
        return None
    module_file = root.joinpath(*parts).with_suffix(".py")
    if module_file.is_file():
        return module_file
    package_init = root.joinpath(*parts, "__init__.py")
    if package_init.is_file():
        return package_init
    return None


def _transitive_apex_import_closure(root: Path, entry: Path) -> set[Path]:
    """Fermeture transitive des imports `apex.*` depuis `entry`, résolue sur le système de
    fichiers — la « vraie » preuve structurelle attendue par la revue J2 (🟠 n°6), par
    opposition à une liste de fichiers écrite à la main.
    """
    visited: set[Path] = set()
    queue = [entry]
    while queue:
        current = queue.pop()
        if current in visited:
            continue
        visited.add(current)
        for module in _imported_apex_modules(current):
            resolved = _module_to_path(root, module)
            if resolved is not None and resolved not in visited:
                queue.append(resolved)
    return visited


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

        Revue J2 (🟠 n°6) : la première version listait 4 fichiers à la main et cherchait la
        sous-chaîne `"ocr.engine"` — une inférence ajoutée dans un module non listé (ex.
        `search_projection.py`, dont `reclassify_ocr.py` dépend réellement) passait sans
        qu'aucun test ne s'en aperçoive. Remplacé par une **vraie fermeture transitive** des
        imports préfixés `apex.` depuis `reclassify_ocr.py` — module par module, résolus sur
        le système de fichiers, pas une liste figée.
        """
        root = Path(__file__).resolve().parents[2] / "src" / "apex"
        entry = root / "queue" / "handlers" / "reclassify_ocr.py"
        closure = _transitive_apex_import_closure(root, entry)

        # Filet anti-régression du filet lui-même : si la résolution de modules se casse
        # silencieusement (ex. changement de layout), la fermeture s'effondre à `{entry}`
        # et le test suivant passerait pour la mauvaise raison.
        assert len(closure) >= 8, (
            f"fermeture transitive suspicieusement petite ({len(closure)} fichiers) : "
            "la résolution des imports `apex.*` a-t-elle échoué silencieusement ? "
            f"{sorted(p.name for p in closure)}"
        )

        engine_path = root / "pipeline" / "ocr" / "engine.py"
        assert engine_path not in closure, (
            "la fermeture transitive des imports de reclassify_ocr.py atteint "
            f"{engine_path} : la re-projection des candidats doit être structurellement "
            "incapable de déclencher une inférence. Chemin d'import à couper : "
            f"{sorted(p.relative_to(root).as_posix() for p in closure)}"
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
