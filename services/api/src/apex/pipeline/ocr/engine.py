"""**Orchestration** (§3-J.2) — l'unique endroit du projet où un modèle est interrogé.

Son contrat est volontairement minuscule : *« quels textes vois-tu dans cette image, et
avec quelle confiance ? »*. Rien d'autre. Pas de numéro de course, pas de pilote, pas de
rattachement : le modèle ne connaît même pas l'existence de la table des engagements.
Tout ce qui suit (`normalize`, `scoring`, `classify`) est du code déterministe.

Moteur retenu (Décision J.1) : **RapidOCR / onnxruntime** — les modèles PP-OCRv4
(détection DB + reconnaissance CRNN) convertis en ONNX, exécutés sur CPU.

- ~15 Mo de poids, installables par `pip` sans binaire système : c'est ce qui le rend
  compatible du plafond de 250 Mo du runtime Python de Vercel, contrairement à EasyOCR
  (PyTorch, ~2 Go) ou PaddleOCR (framework complet). Tesseract, lui, exigerait un binaire
  système absent du runtime — et vise le document, pas le texte peint en scène naturelle.
- Il renvoie **une confiance par boîte**, ce qui est exactement la matière première dont
  la classification par seuils a besoin.
- **Aucun appel réseau, aucun service tiers** : invariant du projet (`AGENTS.md`). Les
  poids sont embarqués dans le paquet installé ; `apex.cli fetch-models` ne fait que les
  recopier dans `OCR_MODEL_DIR` pour un déploiement qui préfère les servir depuis un
  répertoire à lui. Rien n'est téléchargé à l'exécution.

Le moteur est **remplaçable en un fichier** : tout le reste du code ne connaît que le
protocole `OcrEngine` et le type `TextBox`. Si la calibration sur photos réelles déçoit,
on change d'implémentation ici, et l'éval offline (`pytest -m ocr_eval`) tranche.
"""

from __future__ import annotations

import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from PIL import Image

from apex.config import settings
from apex.services.ocr_settings import ENGINE_VERSION_DEFAULT

#: Quadrilatère de détection : 4 sommets `(x, y)` en pixels de l'image analysée.
Quad = tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]


@dataclass(frozen=True, slots=True)
class TextBox:
    """Sortie brute du modèle. **Le seul type que produit la couche probabiliste.**

    `confidence` est la confiance de *reconnaissance* rendue par le moteur — pas le score
    exposé à l'utilisateur, qui est calculé de façon déterministe par `scoring.py`.
    """

    text: str
    confidence: float
    quad: Quad


class OcrEngine(Protocol):
    """Contrat minimal — `read()` et une version, rien de plus."""

    @property
    def version(self) -> str: ...

    def read(self, image: Image.Image) -> list[TextBox]: ...


def _model_overrides() -> dict[str, str]:
    """Poids servis depuis `OCR_MODEL_DIR` s'ils y sont, sinon ceux du paquet installé.

    Aucun téléchargement : le répertoire est soit peuplé par `apex.cli fetch-models`
    (copie locale), soit vide — auquel cas RapidOCR utilise ses poids embarqués.
    """
    directory = Path(settings.ocr_model_dir)
    if not directory.is_dir():
        return {}
    mapping = {
        "det_model_path": "ch_PP-OCRv4_det_infer.onnx",
        "rec_model_path": "ch_PP-OCRv4_rec_infer.onnx",
        "cls_model_path": "ch_ppocr_mobile_v2.0_cls_infer.onnx",
    }
    return {
        key: str(directory / name) for key, name in mapping.items() if (directory / name).is_file()
    }


class RapidOcrEngine:
    """Implémentation par défaut. Chargement **paresseux** des poids ONNX.

    Instancier RapidOCR coûte ~0,4 s (lecture des trois graphes) : on ne le fait qu'au
    premier `read()` réel, pour que l'import du module — fait par tout processus qui
    importe `apex.main` — reste gratuit. Le verrou protège l'initialisation ainsi que
    l'inférence : `onnxruntime` n'offre aucune garantie de ré-entrance sur une même
    session, et le worker peut draîner plusieurs jobs en parallèle (`drain`, 8 threads
    dans le test de concurrence).
    """

    def __init__(self, version: str = ENGINE_VERSION_DEFAULT) -> None:
        self._version = version
        self._lock = threading.Lock()
        self._ocr: Any | None = None

    @property
    def version(self) -> str:
        return self._version

    def _ensure_loaded(self) -> Any:
        if self._ocr is None:
            from rapidocr_onnxruntime import RapidOCR  # import différé : ~0,4 s de chargement

            self._ocr = RapidOCR(**_model_overrides())
        return self._ocr

    def read(self, image: Image.Image) -> list[TextBox]:
        array = np.asarray(image.convert("RGB"))
        with self._lock:
            ocr = self._ensure_loaded()
            raw, _elapsed = ocr(array)
        if not raw:
            return []
        boxes: list[TextBox] = []
        for entry in raw:
            quad_raw, text, confidence = entry[0], entry[1], entry[2]
            points = tuple((float(p[0]), float(p[1])) for p in quad_raw)
            if len(points) != 4:
                # Un quadrilatère non quadrangulaire n'est pas exploitable par le filtrage
                # géométrique — ignoré plutôt que déformé silencieusement.
                continue
            boxes.append(
                TextBox(
                    text=str(text),
                    confidence=float(confidence),
                    quad=(points[0], points[1], points[2], points[3]),
                )
            )
        return boxes


_engine: OcrEngine | None = None
_engine_lock = threading.Lock()


def get_engine() -> OcrEngine:
    """Instance partagée du processus — construite une seule fois, poids chargés au 1ᵉʳ usage."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = RapidOcrEngine()
    return _engine


def set_engine(engine: OcrEngine | None) -> None:
    """Injecte un moteur (tests, évaluation offline, futur remplacement).

    `None` restaure le moteur par défaut. C'est le seul point d'injection du projet : si
    un test peut faire tourner tout le pipeline OCR avec un moteur factice, c'est la
    preuve que la frontière Orchestration / Exécution tient.
    """
    global _engine
    with _engine_lock:
        _engine = engine


def copy_bundled_models(destination: str | Path) -> list[str]:
    """`apex.cli fetch-models` — recopie les poids embarqués vers `destination`.

    Volontairement **hors réseau** : les poids voyagent avec la roue `rapidocr-onnxruntime`
    installée par `uv sync`. Aucune dépendance à un service tiers, même au build.
    """
    import rapidocr_onnxruntime

    source = Path(rapidocr_onnxruntime.__file__).parent / "models"
    target = Path(destination)
    target.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for path in sorted(source.glob("*.onnx")):
        shutil.copy2(path, target / path.name)
        copied.append(path.name)
    return copied
