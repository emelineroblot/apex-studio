"""**Exécution** — filtrage géométrique (§3-J.3, étape 3) et score composite (étape 5).

100 % déterministe : mêmes entrées ⇒ même sortie, sans base ni modèle.

## Filtrage géométrique — ce qu'on refuse de regarder

Une boîte est écartée **avant même d'être normalisée** si :

- son aire sort de `[min_box_area_ratio, max_box_area_ratio]` (défauts : 0,05 % à 8 % de
  l'image) — trop petite, c'est du bruit de compression ; trop grande, c'est un panneau
  publicitaire ou un titre incrusté, pas un numéro peint sur une portière ;
- son rapport largeur/hauteur sort de `[0,15 ; 5,0]` — un numéro de 1 à 3 chiffres, même
  très incliné, ne dégénère pas en trait ;
- son centre tombe dans la bande haute de l'image (10 % par défaut) : le ciel ne porte pas
  de numéro de course.

## Score exposé — la formule affichée dans l'UI

    score = confiance_modèle × f_géométrie × f_longueur × f_pureté       (borné à [0, 1])

- **`confiance_modèle`** : la seule quantité venue du modèle.
- **`f_géométrie`** : pénalise les boîtes anormalement petites (rampe linéaire de 0,55 au
  plancher d'aire jusqu'à 1,0 à huit fois ce plancher) et celles qui touchent un bord de
  l'image (× 0,85), où le numéro est vraisemblablement tronqué.
- **`f_longueur`** : 0,72 pour une lecture d'un seul chiffre, 1,0 au-delà. Une lecture à un
  chiffre est bien plus souvent fausse — un « 1 » isolé peut être n'importe quel montant
  vertical de la carrosserie.
- **`f_pureté`** : **écart assumé au plan**, qui ne prévoyait que les trois premiers
  facteurs. Sans lui, un logo de sponsor lu « SO » avec une confiance de 0,99 devient
  « 50 » à 0,99 et se retrouve **rattaché automatiquement** au n°50 : le faux positif le
  plus grave possible, puisqu'il livre une photo au mauvais client. Le facteur vaut la
  proportion de caractères qui étaient déjà des chiffres avant substitution, planchée à
  0,30 ; il ne coûte rien à une lecture propre (`f_pureté = 1`). Son effet est chiffré dans
  `docs/ocr-eval.md`.

Chaque facteur est renvoyé séparément (`ScoreBreakdown`) : c'est ce qui permet à l'UI
d'expliquer un score au survol plutôt que d'afficher un nombre magique.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apex.pipeline.ocr.engine import Quad, TextBox
from apex.pipeline.ocr.normalize import NormalizedText

#: Rapport largeur/hauteur plausible pour un numéro de 1 à 3 chiffres, inclinaison comprise.
MIN_ASPECT_RATIO = 0.15
MAX_ASPECT_RATIO = 5.0

#: `f_géométrie` : aire à partir de laquelle la boîte ne coûte plus rien (× plancher d'aire).
AREA_COMFORT_FACTOR = 8.0
#: Valeur du facteur d'aire exactement au plancher — en dessous, la boîte est rejetée.
AREA_FLOOR_PENALTY = 0.55
#: Distance au bord (fraction de la dimension) sous laquelle on considère la boîte tronquée.
EDGE_MARGIN_RATIO = 0.005
EDGE_PENALTY = 0.85

#: `f_longueur` : une lecture d'un seul chiffre est bien plus souvent fausse (§3-J.3).
SINGLE_DIGIT_PENALTY = 0.72

#: `f_pureté` : plancher — une lecture entièrement reconstruite garde une chance d'aller
#: en validation humaine, elle ne doit simplement jamais atteindre le seuil haut seule.
PURITY_FLOOR = 0.30


@dataclass(frozen=True, slots=True)
class BoxGeometry:
    """Boîte englobante du quadrilatère, en fractions de l'image (indépendant de la taille)."""

    x: float
    y: float
    width: float
    height: float
    area_ratio: float
    aspect_ratio: float
    touches_edge: bool


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    """Décomposition du score — affichée telle quelle au survol dans l'UI."""

    model_confidence: float
    geometry_factor: float
    length_factor: float
    purity_factor: float
    score: float


def compute_geometry(quad: Quad, image_width: int, image_height: int) -> BoxGeometry:
    """Boîte englobante normalisée. `image_width/height` doivent être non nuls."""
    xs = [point[0] for point in quad]
    ys = [point[1] for point in quad]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)

    width_px = max(x1 - x0, 0.0)
    height_px = max(y1 - y0, 0.0)
    aspect = (width_px / height_px) if height_px > 0 else 0.0

    margin_x = image_width * EDGE_MARGIN_RATIO
    margin_y = image_height * EDGE_MARGIN_RATIO
    touches_edge = (
        x0 <= margin_x
        or y0 <= margin_y
        or x1 >= image_width - margin_x
        or y1 >= image_height - margin_y
    )

    return BoxGeometry(
        x=x0 / image_width,
        y=y0 / image_height,
        width=width_px / image_width,
        height=height_px / image_height,
        area_ratio=(width_px * height_px) / (image_width * image_height),
        aspect_ratio=aspect,
        touches_edge=touches_edge,
    )


def passes_geometry_filter(
    geometry: BoxGeometry,
    *,
    min_box_area_ratio: float,
    max_box_area_ratio: float,
    top_margin_ratio: float,
) -> bool:
    """Filtre binaire — voir la docstring de module pour la justification de chaque borne."""
    if not (min_box_area_ratio <= geometry.area_ratio <= max_box_area_ratio):
        return False
    if not (MIN_ASPECT_RATIO <= geometry.aspect_ratio <= MAX_ASPECT_RATIO):
        return False
    center_y = geometry.y + geometry.height / 2
    return center_y >= top_margin_ratio


def geometry_factor(geometry: BoxGeometry, *, min_box_area_ratio: float) -> float:
    """Rampe linéaire sur l'aire, × pénalité de bord. Toujours dans `]0, 1]`."""
    comfort = min_box_area_ratio * AREA_COMFORT_FACTOR
    if comfort <= min_box_area_ratio:
        area_factor = 1.0
    else:
        progress = (geometry.area_ratio - min_box_area_ratio) / (comfort - min_box_area_ratio)
        progress = min(max(progress, 0.0), 1.0)
        area_factor = AREA_FLOOR_PENALTY + (1.0 - AREA_FLOOR_PENALTY) * progress
    if geometry.touches_edge:
        area_factor *= EDGE_PENALTY
    return area_factor


def length_factor(number: str) -> float:
    return SINGLE_DIGIT_PENALTY if len(number) <= 1 else 1.0


def purity_factor(normalized: NormalizedText) -> float:
    return max(normalized.digit_purity, PURITY_FLOOR)


def compute_score(
    *,
    model_confidence: float,
    geometry: BoxGeometry,
    normalized: NormalizedText,
    min_box_area_ratio: float,
) -> ScoreBreakdown:
    """Applique la formule documentée en tête de module. `normalized.number` requis."""
    assert normalized.number is not None, "compute_score n'a de sens que sur une lecture retenue"
    geo = geometry_factor(geometry, min_box_area_ratio=min_box_area_ratio)
    length = length_factor(normalized.number)
    purity = purity_factor(normalized)
    score = min(max(model_confidence * geo * length * purity, 0.0), 1.0)
    return ScoreBreakdown(
        model_confidence=model_confidence,
        geometry_factor=geo,
        length_factor=length,
        purity_factor=purity,
        score=score,
    )


@dataclass(frozen=True, slots=True)
class Reading:
    """Candidat prêt à être persisté — plus aucune trace du modèle au-delà de ce point."""

    raw_text: str
    normalized_number: str
    score: float
    bbox: dict[str, Any]


def bbox_payload(geometry: BoxGeometry, quad: Quad, image_width: int, image_height: int) -> dict:
    """JSON stocké dans `media_ocr_candidate.bbox`.

    `x/y/w/h` sont **normalisés** (0..1) : le frontend superpose la boîte sur l'aperçu
    quelle que soit la taille d'affichage, sans jamais avoir à connaître la résolution de
    l'image analysée. Le quadrilatère brut (en pixels) est conservé à côté pour le débogage
    et pour un éventuel rendu incliné.
    """
    return {
        "x": round(geometry.x, 6),
        "y": round(geometry.y, 6),
        "w": round(geometry.width, 6),
        "h": round(geometry.height, 6),
        "quad": [[round(px, 2), round(py, 2)] for px, py in quad],
        "image_width": image_width,
        "image_height": image_height,
    }


def extract_readings(
    boxes: list[TextBox],
    *,
    image_width: int,
    image_height: int,
    min_box_area_ratio: float,
    max_box_area_ratio: float,
    top_margin_ratio: float,
) -> list[Reading]:
    """Chaîne déterministe complète : filtrage → normalisation → score.

    Point important pour le rattachement multiple (§3-J.3, étape 7) : plusieurs numéros
    **distincts** dans la même image produisent plusieurs `Reading`, donc plusieurs
    candidats, donc potentiellement plusieurs rattachements. Deux boîtes lisant le **même**
    numéro sont dédoublonnées en gardant la meilleure — deux fois le n°12 dans le cadre,
    c'est une voiture vue deux fois, pas deux voitures.
    """
    if image_width <= 0 or image_height <= 0:
        return []

    from apex.pipeline.ocr.normalize import normalize_text

    best: dict[str, Reading] = {}
    for box in boxes:
        geometry = compute_geometry(box.quad, image_width, image_height)
        if not passes_geometry_filter(
            geometry,
            min_box_area_ratio=min_box_area_ratio,
            max_box_area_ratio=max_box_area_ratio,
            top_margin_ratio=top_margin_ratio,
        ):
            continue
        normalized = normalize_text(box.text)
        if normalized.number is None:
            continue
        breakdown = compute_score(
            model_confidence=box.confidence,
            geometry=geometry,
            normalized=normalized,
            min_box_area_ratio=min_box_area_ratio,
        )
        reading = Reading(
            raw_text=box.text,
            normalized_number=normalized.number,
            score=breakdown.score,
            bbox=bbox_payload(geometry, box.quad, image_width, image_height),
        )
        current = best.get(normalized.number)
        if current is None or reading.score > current.score:
            best[normalized.number] = reading

    return sorted(best.values(), key=lambda r: (-r.score, r.normalized_number))
