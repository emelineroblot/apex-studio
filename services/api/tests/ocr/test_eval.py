"""Évaluation offline de l'OCR sur jeu synthétique annoté (§3-J.5) — **gate bloquant**.

    uv run pytest -m ocr_eval -s

Hors de la suite par défaut (`addopts = -m 'not ocr_eval'`) : ~4 minutes, et surtout aucune
base de données — c'est une mesure du **modèle et de la chaîne déterministe**, pas de l'API.

## Ce qu'on mesure, et pourquoi dans cet ordre

1. **Le taux d'erreur parmi les rattachements automatiques.** C'est la métrique qui décide.
   Un faux positif au-dessus du seuil haut livre une photo au mauvais client : il coûte
   infiniment plus cher qu'une abstention, qui ne coûte qu'un clic. Le seuil haut est donc
   calibré **sous contrainte de précision**, jamais pour maximiser la couverture.
2. Le taux de rattachement automatique, d'envoi en validation, d'abstention — la répartition
   du travail entre la machine et l'humain.
3. La **calibration** : quand le système annonce 0,9, a-t-il raison 9 fois sur 10 ? Un score
   affiché dans l'UI qui ne veut rien dire est pire qu'un score absent.
4. Le **balayage de seuils** : quel couple maximise l'automatique sous `précision ≥ 98 %`.

## Ce que ces chiffres ne disent pas

Ils portent sur un jeu **synthétique**. Les seuils qui en sortent ne seront pas les bons sur
photos réelles — c'est attendu et assumé. Le livrable n'est pas un nombre, c'est un
**protocole** : pointer `OCR_EVAL_DATASET` sur le jeu réel une fois sourcé, rejouer cette
commande, lire les deux nombres, les saisir dans `/settings/ocr`. Aucune ligne de code à
modifier.

## Reproductibilité

Jeu à graine fixe, moteur ONNX déterministe (pas d'échantillonnage) : deux exécutions
donnent les **mêmes** chiffres. `test_engine_is_deterministic` le vérifie plutôt que de
l'affirmer — un score qui bouge d'un run à l'autre n'est pas un score « passé ».
"""

from __future__ import annotations

import json
import math
import os
import statistics
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from apex.demo.synthetic_plates import (
    ENTRY_LIST_SIZE,
    LEVELS,
    PlateSample,
    generate_dataset,
    load_manifest,
)
from apex.pipeline.ocr import classify
from apex.pipeline.ocr.engine import get_engine
from apex.pipeline.ocr.normalize import canonical_number
from apex.pipeline.ocr.scoring import extract_readings
from apex.services import ocr_settings as ocr_defaults

pytestmark = pytest.mark.ocr_eval

REPO_API_ROOT = Path(__file__).resolve().parents[2]
#: Jeu mis en cache hors du dépôt (gitignoré) : re-générer 360 images coûte ~2 min.
DEFAULT_DATASET_DIR = REPO_API_ROOT / ".ocr-eval" / "dataset"
REPORT_PATH = REPO_API_ROOT.parent.parent / "docs" / "ocr-eval.md"

#: Images par niveau de difficulté (6 niveaux). Réglable pour une passe rapide.
PER_LEVEL = int(os.environ.get("OCR_EVAL_PER_LEVEL", "60"))

#: **Cible chiffrée, explicite et bloquante** : la précision dans la bande « rattachement
#: automatique » aux seuils par défaut. En dessous, la feature n'est pas livrable — on
#: relève le seuil haut ou on renonce à l'automatisme, on ne « constate » pas l'écart.
TARGET_AUTO_PRECISION = 0.98

#: Seconde cible, moins critique mais explicite : sans un minimum d'automatisme, la feature
#: ne vaut pas son coût — autant tout envoyer en validation humaine.
TARGET_AUTO_COVERAGE = 0.35


@dataclass(frozen=True, slots=True)
class Candidate:
    number: str
    score: float
    raw_text: str


@dataclass(frozen=True, slots=True)
class Observation:
    """Une image, sa vérité terrain et ce que la chaîne en a tiré — sans aucun seuil appliqué.

    Découplage volontaire : l'inférence coûte 0,35 s par image, le balayage de seuils doit
    pouvoir explorer des dizaines de couples **sans la relancer**. C'est exactement la
    propriété que `reclassify_ocr` exploite en production.
    """

    sample: PlateSample
    candidates: tuple[Candidate, ...]


def _dataset_dir() -> Path:
    override = os.environ.get("OCR_EVAL_DATASET")
    if override:
        return Path(override)
    # Le cache par défaut vit dans l'arbre de travail : il s'auto-ignore, sinon chaque
    # exécution de l'éval laisserait 360 JPEG en « untracked » sous les yeux du prochain
    # `git status`. Écrit ici plutôt que dans le `.gitignore` racine pour que le répertoire
    # reste autoportant : le supprimer ne laisse aucune règle orpheline derrière lui.
    DEFAULT_DATASET_DIR.parent.mkdir(parents=True, exist_ok=True)
    marker = DEFAULT_DATASET_DIR.parent / ".gitignore"
    if not marker.exists():
        marker.write_text(
            "# Cache local de l'évaluation OCR offline — régénérable, jamais versionné.\n*\n",
            encoding="utf-8",
        )
    return DEFAULT_DATASET_DIR


@pytest.fixture(scope="session")
def dataset() -> tuple[list[PlateSample], tuple[str, ...]]:
    """Génère (ou relit) le jeu **et sa table des engagements**."""
    directory = _dataset_dir()
    cached = load_manifest(directory)
    if cached is not None and len(cached[0]) == PER_LEVEL * len(LEVELS):
        print(f"\n[eval] jeu relu depuis le cache : {len(cached[0])} images ({directory})")
        return cached
    started = time.monotonic()
    samples = generate_dataset(directory, per_level=PER_LEVEL)
    print(f"\n[eval] jeu genere : {len(samples)} images en {time.monotonic() - started:.1f} s")
    reloaded = load_manifest(directory)
    assert reloaded is not None
    return reloaded


@pytest.fixture(scope="session")
def entry_list(dataset: tuple[list[PlateSample], tuple[str, ...]]) -> set[str]:
    """Le plateau : les voitures réellement au départ, sous forme canonique.

    C'est la table des engagements du shooting simulé, et sa **taille** est le principal
    garde-fou métier contre les faux positifs : un numéro mal lu tombe le plus souvent hors
    du plateau, et part alors en incohérence plutôt que chez le mauvais client.
    """
    return {canonical_number(number) for number in dataset[1]}


@pytest.fixture(scope="session")
def observations(dataset: tuple[list[PlateSample], tuple[str, ...]]) -> list[Observation]:
    """Exécute l'inférence une seule fois pour toute la session."""
    directory = _dataset_dir()
    samples = dataset[0]
    engine = get_engine()
    started = time.monotonic()
    results: list[Observation] = []
    for sample in samples:
        with Image.open(directory / sample.filename) as image:
            image.load()
            boxes = engine.read(image)
            readings = extract_readings(
                boxes,
                image_width=image.width,
                image_height=image.height,
                min_box_area_ratio=ocr_defaults.MIN_BOX_AREA_RATIO_DEFAULT,
                max_box_area_ratio=ocr_defaults.MAX_BOX_AREA_RATIO_DEFAULT,
                top_margin_ratio=ocr_defaults.TOP_MARGIN_RATIO_DEFAULT,
            )
        results.append(
            Observation(
                sample=sample,
                candidates=tuple(
                    Candidate(r.normalized_number, r.score, r.raw_text) for r in readings
                ),
            )
        )
    elapsed = time.monotonic() - started
    print(
        f"[eval] inference : {len(results)} images en {elapsed:.1f} s "
        f"({elapsed / max(len(results), 1) * 1000:.0f} ms/image)"
    )
    return results


@dataclass(frozen=True, slots=True)
class Outcome:
    bucket: str
    correct: bool | None
    auto_numbers: tuple[str, ...]


def _classify_image(
    observation: Observation, plateau: set[str], *, high: float, low: float
) -> Outcome:
    """Applique `classify.decide` — **la règle de production, pas une copie** — puis résume.

    Résumé au niveau de l'image, parce que c'est l'unité que voit l'utilisateur : une photo
    est rattachée automatiquement, part en validation, ou reste en attente.
    """
    truth = canonical_number(observation.sample.number) if observation.sample.number else None
    decisions = [
        (
            classify.decide(
                matched=canonical_number(candidate.number) in plateau,
                score=candidate.score,
                high=high,
                low=low,
            ),
            candidate,
        )
        for candidate in observation.candidates
    ]

    auto = [
        candidate for resolution, candidate in decisions if resolution == classify.RESOLUTION_AUTO
    ]
    if auto:
        numbers = tuple(canonical_number(candidate.number) for candidate in auto)
        # Une photo est « juste » si **tous** ses rattachements automatiques sont justes :
        # un rattachement correct n'excuse pas un rattachement erroné à côté, qui livrerait
        # quand même la photo à un client qui n'y a pas droit.
        correct = truth is not None and all(number == truth for number in numbers)
        return Outcome("auto", correct, numbers)

    resolutions = {resolution for resolution, _ in decisions}
    if classify.RESOLUTION_REVIEW in resolutions:
        return Outcome("review", None, ())
    if classify.RESOLUTION_NOT_ENGAGED in resolutions:
        return Outcome("not_engaged", None, ())
    if decisions:
        return Outcome("abstain", None, ())
    return Outcome("no_reading", None, ())


@dataclass(frozen=True, slots=True)
class Metrics:
    total: int
    buckets: dict[str, int]
    auto_precision: float
    auto_coverage: float
    errors: tuple[tuple[str, int, str | None, tuple[str, ...]], ...]

    @property
    def auto_error_rate(self) -> float:
        return 1.0 - self.auto_precision


def _measure(observations: list[Observation], plateau: set[str], *, high: float, low: float):
    buckets: Counter[str] = Counter()
    auto_total = 0
    auto_correct = 0
    errors: list[tuple[str, int, str | None, tuple[str, ...]]] = []
    for observation in observations:
        outcome = _classify_image(observation, plateau, high=high, low=low)
        buckets[outcome.bucket] += 1
        if outcome.bucket == "auto":
            auto_total += 1
            if outcome.correct:
                auto_correct += 1
            else:
                truth = (
                    canonical_number(observation.sample.number)
                    if observation.sample.number
                    else None
                )
                errors.append(
                    (
                        observation.sample.filename,
                        observation.sample.level,
                        truth,
                        outcome.auto_numbers,
                    )
                )
    total = len(observations)
    return Metrics(
        total=total,
        buckets=dict(buckets),
        auto_precision=(auto_correct / auto_total) if auto_total else 1.0,
        auto_coverage=(auto_total / total) if total else 0.0,
        errors=tuple(errors),
    )


def _calibration(
    observations: list[Observation], plateau: set[str]
) -> list[tuple[str, int, float]]:
    """Score annoncé vs justesse observée, par tranche de 0,1.

    Ne porte que sur les candidats dont le numéro **existe** au plateau : c'est la seule
    population où « juste / faux » a un sens de rattachement.
    """
    buckets: dict[int, list[bool]] = {index: [] for index in range(10)}
    for observation in observations:
        truth = canonical_number(observation.sample.number) if observation.sample.number else None
        for candidate in observation.candidates:
            number = canonical_number(candidate.number)
            if number not in plateau:
                continue
            index = min(int(candidate.score * 10), 9)
            buckets[index].append(number == truth)
    rows = []
    for index in range(10):
        values = buckets[index]
        label = f"[{index / 10:.1f} – {(index + 1) / 10:.1f}["
        rows.append((label, len(values), (sum(values) / len(values)) if values else float("nan")))
    return rows


def _sweep(observations: list[Observation], plateau: set[str]) -> list[tuple[float, Metrics]]:
    thresholds = [round(0.50 + 0.05 * step, 2) for step in range(11)]
    return [
        (high, _measure(observations, plateau, high=high, low=ocr_defaults.OCR_LOW_DEFAULT))
        for high in thresholds
    ]


def _best_high(sweep: list[tuple[float, Metrics]]) -> tuple[float, Metrics] | None:
    """Couverture maximale **sous contrainte** de précision — l'ordre des priorités du projet."""
    eligible = [entry for entry in sweep if entry[1].auto_precision >= TARGET_AUTO_PRECISION]
    if not eligible:
        return None
    return max(eligible, key=lambda entry: (entry[1].auto_coverage, -entry[0]))


def _precision_margin(precision: float, count: int) -> float:
    """Demi-intervalle de confiance à 95 % (approximation normale) sur une proportion.

    Sert à rappeler, dans le rapport, qu'une précision mesurée sur quelques centaines de cas
    n'a pas trois décimales significatives. Sans ce garde-fou de lecture, on conclurait que
    98,05 % « bat » 97,99 % alors que les deux sont indiscernables.
    """
    if count <= 0:
        return 0.0
    return 1.96 * math.sqrt(max(precision * (1 - precision), 0.0) / count)


def _fmt_pct(value: float) -> str:
    return "n/a" if value != value else f"{value * 100:.1f} %"


def _write_report(
    observations: list[Observation],
    plateau: set[str],
    default_metrics: Metrics,
    sweep: list[tuple[float, Metrics]],
    best: tuple[float, Metrics] | None,
) -> None:
    per_level = []
    for level in LEVELS:
        subset = [o for o in observations if o.sample.level == level.index]
        per_level.append(
            (
                level,
                _measure(
                    subset,
                    plateau,
                    high=ocr_defaults.OCR_HIGH_DEFAULT,
                    low=ocr_defaults.OCR_LOW_DEFAULT,
                ),
            )
        )

    lines: list[str] = []
    lines.append("# Évaluation offline de l'OCR — jeu synthétique\n")
    lines.append(
        "> Rapport **généré** par `uv run pytest -m ocr_eval`. Ne pas éditer à la main : "
        "toute modification est écrasée à la prochaine exécution.\n"
    )
    lines.append(f"- Généré le : {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(
        f"- Jeu : {len(observations)} images synthétiques, {len(LEVELS)} niveaux, graine fixe"
    )
    lines.append(
        f"- Table des engagements simulée : **{len(plateau)} voitures au départ** — "
        "paramètre décisif, cf. « Limites »"
    )
    lines.append(
        f"- Seuils évalués : `ocr_high = {ocr_defaults.OCR_HIGH_DEFAULT}`, "
        f"`ocr_low = {ocr_defaults.OCR_LOW_DEFAULT}`"
    )
    lines.append(
        f"- Cible bloquante : précision ≥ {TARGET_AUTO_PRECISION * 100:.0f} % dans la bande « auto »\n"
    )

    lines.append("## Résultat aux seuils par défaut\n")
    lines.append("| Indicateur | Valeur |")
    lines.append("|---|---|")
    lines.append(
        f"| Rattachement automatique | {_fmt_pct(default_metrics.auto_coverage)} des images |"
    )
    lines.append(
        f"| **Précision dans la bande auto** | **{_fmt_pct(default_metrics.auto_precision)}** |"
    )
    lines.append(
        f"| **Taux d'erreur parmi les rattachements auto** | **{_fmt_pct(default_metrics.auto_error_rate)}** |"
    )
    for bucket, label in (
        ("review", "Envoyé en validation humaine"),
        ("not_engaged", "Numéro lu hors table des engagements (incohérence)"),
        ("abstain", "Abstention (score sous le seuil bas)"),
        ("no_reading", "Aucune lecture exploitable"),
    ):
        count = default_metrics.buckets.get(bucket, 0)
        lines.append(f"| {label} | {_fmt_pct(count / default_metrics.total)} ({count}) |")
    lines.append("")

    lines.append("## Par niveau de difficulté\n")
    lines.append(
        "| Niveau | Auto | Précision auto | Validation | Incohérence | Abstention | Rien lu |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for level, metrics in per_level:
        lines.append(
            f"| {level.index} — {level.label} | {_fmt_pct(metrics.auto_coverage)} | "
            f"{_fmt_pct(metrics.auto_precision)} | "
            f"{metrics.buckets.get('review', 0)} | {metrics.buckets.get('not_engaged', 0)} | "
            f"{metrics.buckets.get('abstain', 0)} | {metrics.buckets.get('no_reading', 0)} |"
        )
    lines.append("")

    lines.append("## Calibration — score annoncé vs justesse observée\n")
    lines.append(
        "Le score affiché dans l'UI doit vouloir dire quelque chose. Lecture : parmi les "
        "candidats dont le numéro figure au plateau, part de lectures exactes par tranche.\n"
    )
    lines.append("| Tranche de score | Candidats | Justesse observée |")
    lines.append("|---|---|---|")
    for label, count, accuracy in _calibration(observations, plateau):
        lines.append(f"| {label} | {count} | {_fmt_pct(accuracy)} |")
    lines.append("")

    lines.append("## Balayage du seuil haut\n")
    lines.append(
        f"`ocr_low` fixé à {ocr_defaults.OCR_LOW_DEFAULT}. On cherche la **couverture maximale "
        f"sous contrainte de précision ≥ {TARGET_AUTO_PRECISION * 100:.0f} %** — jamais l'inverse.\n"
    )
    lines.append("| `ocr_high` | Auto | Précision auto | Erreurs auto | Tient la cible |")
    lines.append("|---|---|---|---|---|")
    for high, metrics in sweep:
        eligible = metrics.auto_precision >= TARGET_AUTO_PRECISION
        # Précision au centième : à l'arrondi au dixième, 97,95 % et 98,04 % s'affichent
        # tous deux « 98,0 % » alors qu'un seul tient la cible — un lecteur du rapport ne
        # doit jamais avoir à deviner pourquoi une ligne est cochée et l'autre non.
        lines.append(
            f"| {high:.2f} | {_fmt_pct(metrics.auto_coverage)} | "
            f"{metrics.auto_precision * 100:.2f} % | {len(metrics.errors)} | "
            f"{'oui' if eligible else 'non'} |"
        )
    lines.append("")
    if best is not None:
        auto_count = best[1].buckets.get("auto", 0)
        margin = _precision_margin(best[1].auto_precision, auto_count)
        lines.append(
            f"**Couple recommandé sur ce jeu : `ocr_high = {best[0]:.2f}`, "
            f"`ocr_low = {ocr_defaults.OCR_LOW_DEFAULT}`** — "
            f"{_fmt_pct(best[1].auto_coverage)} d'automatique à "
            f"{_fmt_pct(best[1].auto_precision)} de précision.\n"
        )
        lines.append(
            "⚠️ **La colonne de précision n'est pas monotone, et c'est attendu.** Relever le "
            f"seuil retire d'abord des lectures justes : sur {auto_count} rattachements "
            f"automatiques, une seule erreur pèse {100 / max(auto_count, 1):.2f} point. "
            "L'intervalle de confiance à 95 % autour de la précision mesurée vaut environ "
            f"±{margin * 100:.1f} point(s) — le seuil recommandé est un **ordre de grandeur**, "
            "pas une valeur à trois décimales. Agrandir le jeu (`OCR_EVAL_PER_LEVEL`) resserre "
            "l'estimation.\n"
        )
    else:
        lines.append(
            "**Aucun seuil ne tient la contrainte de précision sur ce jeu.** "
            "La feature n'est pas livrable en rattachement automatique en l'état.\n"
        )

    lines.append("## Les erreurs, une par une\n")
    lines.append(
        "Ce sont les cas qui coûtent cher : une photo rattachée au mauvais engagement part "
        "chez le mauvais client. On les liste plutôt que de les résumer.\n"
    )
    if default_metrics.errors:
        lines.append("| Image | Niveau | Numéro réel | Numéro rattaché |")
        lines.append("|---|---|---|---|")
        for filename, level, truth, read in default_metrics.errors:
            lines.append(
                f"| `{filename}` | {level} | {truth or '— (aucun numéro)'} | {', '.join(read)} |"
            )
    else:
        lines.append("_Aucune erreur dans la bande « auto » sur cette exécution._")
    lines.append("")

    lines.append("## Limites — à lire avant de citer un chiffre\n")
    lines.append(
        "- **Jeu synthétique.** Numéros rendus par code sur une carrosserie stylisée. Les "
        "photos réelles apportent reflets, salissures, angles extrêmes et lettrages "
        "publicitaires bien plus variés. Ces chiffres sont un plancher de sanité, pas une "
        "prédiction.\n"
        "- **Les seuils calibrés ici ne seront pas les bons sur photos réelles.** C'est prévu : "
        "ils vivent en base (`app_setting`), se changent depuis l'UI, et leur changement "
        "re-projette les candidats existants **sans relancer aucune inférence**.\n"
        "- **Protocole de recalibrage** : `OCR_EVAL_DATASET=/chemin/vers/jeu-reel "
        "uv run pytest -m ocr_eval -s`, lire le couple recommandé ci-dessus, le saisir dans "
        "`/settings/ocr`. Aucune ligne de code à modifier.\n"
        "- **Ce que le taux d'abstention veut dire** : le système renonce plutôt que de "
        "deviner. Une abstention coûte un clic ; un faux positif coûte une photo livrée au "
        "mauvais client. Le déséquilibre est assumé et c'est lui qui pilote la calibration.\n"
    )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def test_offline_evaluation_meets_target(
    observations: list[Observation], entry_list: set[str]
) -> None:
    """**Gate bloquant** : sous la cible, la feature n'est pas livrable."""
    plateau = entry_list
    default_metrics = _measure(
        observations,
        plateau,
        high=ocr_defaults.OCR_HIGH_DEFAULT,
        low=ocr_defaults.OCR_LOW_DEFAULT,
    )
    sweep = _sweep(observations, plateau)
    best = _best_high(sweep)
    _write_report(observations, plateau, default_metrics, sweep, best)

    print("\n" + "=" * 78)
    print(f"[eval] images                      : {default_metrics.total}")
    print(f"[eval] rattachement automatique    : {_fmt_pct(default_metrics.auto_coverage)}")
    print(f"[eval] precision bande auto        : {_fmt_pct(default_metrics.auto_precision)}")
    print(
        f"[eval] ERREURS bande auto          : {len(default_metrics.errors)} "
        f"({_fmt_pct(default_metrics.auto_error_rate)})"
    )
    for bucket in ("review", "not_engaged", "abstain", "no_reading"):
        count = default_metrics.buckets.get(bucket, 0)
        print(f"[eval] {bucket:<27}: {_fmt_pct(count / default_metrics.total)} ({count})")
    if best is not None:
        print(
            f"[eval] seuil haut recommande       : {best[0]:.2f} -> "
            f"{_fmt_pct(best[1].auto_coverage)} auto a {_fmt_pct(best[1].auto_precision)}"
        )
    print(f"[eval] rapport ecrit               : {REPORT_PATH}")
    print("=" * 78)

    assert default_metrics.auto_precision >= TARGET_AUTO_PRECISION, (
        f"Précision dans la bande « rattachement automatique » : "
        f"{_fmt_pct(default_metrics.auto_precision)} < cible {_fmt_pct(TARGET_AUTO_PRECISION)}. "
        f"{len(default_metrics.errors)} photo(s) rattachée(s) au mauvais engagement : "
        f"{[error[0] for error in default_metrics.errors]}. "
        "Relever `ocr_high` (voir le balayage dans docs/ocr-eval.md) ou renoncer à "
        "l'automatisme — ne pas livrer en l'état."
    )
    assert default_metrics.auto_coverage >= TARGET_AUTO_COVERAGE, (
        f"Seulement {_fmt_pct(default_metrics.auto_coverage)} de rattachement automatique "
        f"(cible {_fmt_pct(TARGET_AUTO_COVERAGE)}) : à ce niveau, la file de validation "
        "absorbe tout le travail et l'OCR ne vaut pas son coût."
    )


def test_engine_is_deterministic(observations: list[Observation]) -> None:
    """Stabilité (`pass^k`) : le même jeu relu deux fois doit donner **exactement** la même chose.

    Le moteur est un graphe ONNX exécuté sans échantillonnage — la reproductibilité est
    attendue, mais on la vérifie plutôt que de la supposer : un score qui varie d'un run à
    l'autre invaliderait toute la calibration, et donc les seuils par défaut.
    """
    directory = _dataset_dir()
    engine = get_engine()
    sampled = observations[:: max(len(observations) // 12, 1)]
    for observation in sampled:
        with Image.open(directory / observation.sample.filename) as image:
            image.load()
            boxes = engine.read(image)
            readings = extract_readings(
                boxes,
                image_width=image.width,
                image_height=image.height,
                min_box_area_ratio=ocr_defaults.MIN_BOX_AREA_RATIO_DEFAULT,
                max_box_area_ratio=ocr_defaults.MAX_BOX_AREA_RATIO_DEFAULT,
                top_margin_ratio=ocr_defaults.TOP_MARGIN_RATIO_DEFAULT,
            )
        replay = tuple(Candidate(r.normalized_number, r.score, r.raw_text) for r in readings)
        assert replay == observation.candidates, (
            f"Lecture non reproductible sur {observation.sample.filename} : "
            f"{observation.candidates} puis {replay}."
        )


def test_evaluation_artifacts_are_readable(
    observations: list[Observation], entry_list: set[str]
) -> None:
    """Le jeu et son manifeste doivent rester relisables : c'est ce qui rend l'éval rejouable."""
    directory = _dataset_dir()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["samples"], "manifeste vide"
    assert len(entry_list) == ENTRY_LIST_SIZE, "table des engagements incomplète"
    truths = {o.sample.number for o in observations if o.sample.number}
    assert {canonical_number(t) for t in truths} <= entry_list, (
        "toute voiture photographiée doit figurer au plateau — sinon la mesure des "
        "incohérences compte des cas qui n'existent pas sur un vrai week-end"
    )
    negatives = [o for o in observations if o.sample.number is None]
    assert negatives, "aucune image sans numéro : les faux positifs ne seraient pas mesurés"
    scores = [c.score for o in observations for c in o.candidates]
    assert scores, "aucun candidat produit sur tout le jeu"
    assert min(scores) >= 0.0 and max(scores) <= 1.0, "score hors de [0, 1]"
    print(f"\n[eval] score médian des candidats : {statistics.median(scores):.3f}")
