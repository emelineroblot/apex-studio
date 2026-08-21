"""Jeu synthétique de numéros de course, avec **vérité terrain** (§3-J.5 du plan).

Le jeu de ~300 photos réelles libres de droits n'est pas sourcé (contrainte du brief).
L'OCR est donc développé et mesuré contre des images **générées**, ce qui a trois vertus :

- la vérité terrain est exacte par construction — pas d'annotation manuelle à contester ;
- les dégradations sont **paramétrées** : on sait exactement à quelle difficulté un score
  s'effondre, ce qu'aucun jeu réel non annoté ne dirait ;
- tout est **à graine fixe** : deux exécutions produisent le même jeu, donc les mêmes
  chiffres. Une évaluation qui varie d'un run à l'autre n'est pas une évaluation.

Six niveaux de difficulté, du studio à l'inexploitable. Chaque niveau empile : rotation,
perspective, flou de bougé directionnel, bruit gaussien, sur/sous-exposition, occlusion
partielle, et des tailles de texte décroissantes.

Deux populations sont volontairement présentes en plus des numéros nets :

- des **lettrages de sponsor** (« PIRELLI », « SHELL », « BOSS ») sur la carrosserie, qui
  piègent la normalisation par confusions typographiques (`S→5`, `O→0`, `B→8`) ;
- des images **sans aucun numéro**, pour mesurer ce que le système invente quand il n'y a
  rien à lire. Un faux positif y est bien plus grave qu'une abstention.

⚠️ Ce que ce jeu **n'est pas** : une prédiction de la performance sur photos réelles. Les
seuils qui en sortent sont un point de départ ; le livrable est le **protocole** (rejouer
`pytest -m ocr_eval` sur le jeu réel, lire deux nombres, les saisir dans l'UI).
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

#: Taille de l'aperçu 1600 px — exactement ce que lit `handlers/ocr_media.py` en production.
IMAGE_SIZE = (1600, 1067)

#: On rend 25 % plus large, puis on recadre au centre **après** les dégradations. Sans ce
#: sur-cadre, rotation et perspective laissent des bandes de remplissage sur les bords :
#: des arêtes rectilignes très contrastées, que le détecteur de texte prend volontiers pour
#: des boîtes. Elles n'existent sur aucune photo réelle — les laisser reviendrait à mesurer
#: un artefact du générateur plutôt que la difficulté qu'on prétend simuler.
CANVAS_SIZE = (2000, 1334)


#: Police : celle qu'embarque Pillow (Aileron), redimensionnable et **identique sur toutes
#: les machines**. Dépendre d'une police système (Arial…) rendrait le jeu non reproductible
#: d'un poste à l'autre, ce qui ruinerait la comparabilité des chiffres.
def _font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


#: Lettrages de sponsor — choisis pour leur pouvoir de nuisance sur la normalisation :
#: chacun contient au moins une lettre de la table des confusions (`S`, `O`, `B`, `I`, `Z`).
SPONSORS = ("PIRELLI", "SHELL", "BOSS", "OZ", "SPARCO", "BILSTEIN", "SO", "IB")

#: Couleurs de carrosserie et de numéro — contraste toujours réel, jamais dégénéré.
BODY_COLORS = (
    (198, 32, 38),
    (24, 62, 140),
    (240, 240, 240),
    (18, 18, 22),
    (245, 196, 20),
    (16, 122, 88),
)


@dataclass(frozen=True, slots=True)
class Level:
    """Réglage d'un niveau de difficulté. Tout est ici, rien n'est dispersé dans le code."""

    index: int
    label: str
    text_height: tuple[int, int]
    rotation_deg: float
    perspective: float
    motion_blur_px: int
    noise_sigma: float
    exposure: tuple[float, float]
    occlusion: float
    sponsor_probability: float


LEVELS: tuple[Level, ...] = (
    Level(0, "studio", (120, 140), 0.0, 0.00, 0, 0.0, (1.0, 1.0), 0.0, 0.0),
    Level(1, "propre", (100, 130), 6.0, 0.02, 1, 2.0, (0.95, 1.05), 0.0, 0.35),
    Level(2, "piste", (80, 115), 12.0, 0.05, 3, 5.0, (0.85, 1.15), 0.08, 0.6),
    Level(3, "vitesse", (60, 95), 18.0, 0.09, 5, 9.0, (0.75, 1.25), 0.16, 0.8),
    Level(4, "difficile", (44, 75), 25.0, 0.13, 7, 14.0, (0.65, 1.35), 0.25, 0.9),
    Level(5, "limite", (30, 55), 25.0, 0.18, 9, 20.0, (0.55, 1.45), 0.35, 1.0),
)

#: Proportion d'images **sans numéro** dans chaque niveau — la population qui mesure les
#: faux positifs, celle qui compte le plus (une photo livrée au mauvais client).
NEGATIVE_RATIO = 0.12


@dataclass(frozen=True, slots=True)
class PlateSample:
    """Une image et sa vérité terrain. `number is None` ⇒ il n'y a rien à lire."""

    filename: str
    level: int
    level_label: str
    number: str | None
    text_height: int
    rotation_deg: float
    motion_blur_px: int
    occlusion: float
    sponsor: str | None


def _perspective_coefficients(
    source: list[tuple[float, float]], target: list[tuple[float, float]]
) -> tuple[float, ...]:
    """Coefficients de `Image.transform(..., Image.PERSPECTIVE, coeffs)`.

    Pillow attend la transformation **inverse** (destination → source) : on résout donc le
    système 8×8 dans ce sens. Sans cela l'image part de travers sans erreur visible, ce qui
    fausserait silencieusement toute l'évaluation.
    """
    matrix = []
    for (sx, sy), (tx, ty) in zip(source, target, strict=True):
        matrix.append([tx, ty, 1, 0, 0, 0, -sx * tx, -sx * ty])
        matrix.append([0, 0, 0, tx, ty, 1, -sy * tx, -sy * ty])
    a = np.array(matrix, dtype=np.float64)
    b = np.array(source, dtype=np.float64).reshape(8)
    solution = np.linalg.solve(a, b)
    return tuple(float(value) for value in solution)


def _motion_blur(image: Image.Image, length: int, angle_deg: float) -> Image.Image:
    """Flou de bougé **directionnel** — une voiture en vitesse filée, pas un flou gaussien.

    Implémenté par moyenne de copies décalées le long de la direction : `ImageFilter.Kernel`
    de Pillow plafonne à 5×5, insuffisant pour les 9 px du niveau le plus dur.
    """
    if length <= 1:
        return image
    radians = math.radians(angle_deg)
    dx, dy = math.cos(radians), math.sin(radians)
    array = np.asarray(image, dtype=np.float64)
    accumulator = np.zeros_like(array)
    for step in range(length):
        offset = step - (length - 1) / 2
        shifted = np.roll(array, (int(round(dy * offset)), int(round(dx * offset))), axis=(0, 1))
        accumulator += shifted
    accumulator /= length
    return Image.fromarray(np.clip(accumulator, 0, 255).astype(np.uint8))


def _apply_noise(image: Image.Image, sigma: float, rng: random.Random) -> Image.Image:
    if sigma <= 0:
        return image
    generator = np.random.default_rng(rng.getrandbits(32))
    array = np.asarray(image, dtype=np.float64)
    array += generator.normal(0.0, sigma, array.shape)
    return Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))


def _draw_scene(
    draw: ImageDraw.ImageDraw, rng: random.Random, body_color: tuple[int, int, int]
) -> tuple[int, int, int, int]:
    """Fond (ciel + piste) et carrosserie. Renvoie la boîte de la carrosserie."""
    width, height = CANVAS_SIZE
    horizon = int(height * rng.uniform(0.22, 0.34))
    for y in range(horizon):
        shade = 150 + int(70 * y / max(horizon, 1))
        draw.line([(0, y), (width, y)], fill=(shade - 30, shade - 10, shade + 20))
    for y in range(horizon, height):
        shade = 70 + int(40 * (y - horizon) / max(height - horizon, 1))
        draw.line([(0, y), (width, y)], fill=(shade, shade, shade + 4))
    # Vibreur rouge/blanc en bord de piste : texture réaliste, et distracteur géométrique.
    kerb_y = horizon + int(height * 0.06)
    for i in range(0, width, 120):
        draw.rectangle(
            [i, kerb_y, i + 60, kerb_y + 26],
            fill=(200, 40, 40) if (i // 120) % 2 == 0 else (235, 235, 235),
        )

    body_w = int(width * rng.uniform(0.45, 0.62))
    body_h = int(body_w * rng.uniform(0.34, 0.44))
    x0 = int((width - body_w) * rng.uniform(0.2, 0.8))
    y0 = int(horizon + (height - horizon - body_h) * rng.uniform(0.25, 0.6))
    draw.rounded_rectangle([x0, y0, x0 + body_w, y0 + body_h], radius=40, fill=body_color)
    # Vitrage : une zone sombre qui casse l'aplat et donne du contexte au détecteur.
    draw.polygon(
        [
            (x0 + int(body_w * 0.30), y0 + int(body_h * 0.10)),
            (x0 + int(body_w * 0.72), y0 + int(body_h * 0.10)),
            (x0 + int(body_w * 0.66), y0 + int(body_h * 0.40)),
            (x0 + int(body_w * 0.34), y0 + int(body_h * 0.40)),
        ],
        fill=(30, 34, 42),
    )
    return x0, y0, body_w, body_h


def render_sample(
    sample_index: int, level: Level, seed: int, entry_list: tuple[str, ...] | None = None
) -> tuple[Image.Image, PlateSample]:
    """Rend une image et sa vérité terrain. Déterministe pour `(sample_index, level, seed)`.

    Le numéro est **tiré de la table des engagements** : sur un vrai week-end, toute voiture
    photographiée est au départ. C'est la lecture qui peut se tromper, pas la présence.
    """
    entry_list = entry_list if entry_list is not None else build_entry_list(seed)
    rng = random.Random((seed * 100_003) + (level.index * 1_009) + sample_index)

    is_negative = rng.random() < NEGATIVE_RATIO
    number = None if is_negative else rng.choice(entry_list)
    text_height = rng.randint(*level.text_height)
    body_color = rng.choice(BODY_COLORS)
    # Numéro clair sur carrosserie sombre et inversement — un contraste toujours lisible en
    # principe : la difficulté doit venir des dégradations, pas d'un choix de couleur absurde.
    luminance = 0.299 * body_color[0] + 0.587 * body_color[1] + 0.114 * body_color[2]
    ink = (18, 18, 20) if luminance > 140 else (245, 245, 245)

    image = Image.new("RGB", CANVAS_SIZE, (120, 140, 170))
    draw = ImageDraw.Draw(image)
    x0, y0, body_w, body_h = _draw_scene(draw, rng, body_color)

    sponsor = None
    if rng.random() < level.sponsor_probability:
        sponsor = rng.choice(SPONSORS)
        sponsor_font = _font(max(int(text_height * rng.uniform(0.35, 0.6)), 16))
        draw.text(
            (x0 + int(body_w * 0.08), y0 + int(body_h * 0.72)),
            sponsor,
            fill=ink,
            font=sponsor_font,
        )

    if number is not None:
        font = _font(text_height)
        bbox = draw.textbbox((0, 0), number, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        # Panneau porte-numéro (le cercle blanc réglementaire), centré sur la portière.
        cx = x0 + int(body_w * rng.uniform(0.42, 0.60))
        cy = y0 + int(body_h * rng.uniform(0.48, 0.62))
        pad = int(text_h * 0.45)
        draw.ellipse(
            [
                cx - text_w // 2 - pad,
                cy - text_h // 2 - pad,
                cx + text_w // 2 + pad,
                cy + text_h // 2 + pad,
            ],
            fill=(250, 250, 250) if ink[0] < 128 else (20, 20, 24),
        )
        draw.text(
            (cx - text_w // 2 - bbox[0], cy - text_h // 2 - bbox[1]),
            number,
            fill=(20, 20, 24) if ink[0] < 128 else (250, 250, 250),
            font=font,
        )
        if level.occlusion > 0:
            _occlude(draw, cx, cy, text_w, text_h, level.occlusion, rng, body_color)

    image = _crop_to_preview(_degrade(image, level, rng))
    return image, PlateSample(
        filename=f"L{level.index}_{sample_index:04d}.jpg",
        level=level.index,
        level_label=level.label,
        number=number,
        text_height=text_height,
        rotation_deg=level.rotation_deg,
        motion_blur_px=level.motion_blur_px,
        occlusion=level.occlusion,
        sponsor=sponsor,
    )


#: Taille du plateau simulé. **Point de réalisme décisif de toute l'évaluation** : un
#: week-end de course aligne quelques dizaines de voitures, pas plusieurs centaines. Un
#: plateau artificiellement dense fausse la mesure dans le mauvais sens — il transforme
#: chaque lecture tronquée (« 485 » dont le dernier chiffre est masqué, lu « 48 ») en
#: rattachement au mauvais engagement, là où un vrai plateau la renverrait presque toujours
#: dans le bac « incohérence ». Autrement dit : la densité du plateau *est* le principal
#: garde-fou métier contre les faux positifs, et la simuler correctement n'est pas une
#: complaisance, c'est la condition pour que le chiffre veuille dire quelque chose.
ENTRY_LIST_SIZE = 44

#: Part des numéros à trois chiffres — quelques séries d'endurance en utilisent, la plupart
#: des plateaux restent en 1-99.
THREE_DIGIT_SHARE = 0.35


def build_entry_list(seed: int) -> tuple[str, ...]:
    """La **table des engagements** du week-end simulé : les voitures réellement au départ.

    Quelques numéros sont écrits avec un zéro de tête (« 07 ») comme le font certaines
    fédérations : de quoi éprouver la canonicalisation de la jointure.
    """
    rng = random.Random(seed ^ 0x5EED_C0DE)
    values: dict[int, str] = {}
    while len(values) < ENTRY_LIST_SIZE:
        if rng.random() < THREE_DIGIT_SHARE:
            number = rng.randint(100, 999)
            written = str(number)
        else:
            number = rng.randint(1, 99)
            written = f"{number:02d}" if number < 10 and rng.random() < 0.5 else str(number)
        values.setdefault(number, written)
    return tuple(values[key] for key in sorted(values))


def _occlude(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    text_w: float,
    text_h: float,
    fraction: float,
    rng: random.Random,
    body_color: tuple[int, int, int],
) -> None:
    """Occlusion partielle du numéro — un rétroviseur, un pilote, un autre concurrent."""
    covered_w = int(text_w * fraction)
    if covered_w <= 0:
        return
    from_left = rng.random() < 0.5
    left = cx - text_w // 2 if from_left else cx + text_w // 2 - covered_w
    draw.rectangle(
        [left, cy - text_h, left + covered_w, cy + text_h],
        fill=tuple(max(0, channel - 25) for channel in body_color),
    )


def _crop_to_preview(image: Image.Image) -> Image.Image:
    """Recadre au centre à la taille d'aperçu — élimine les bandes de bord (cf. `CANVAS_SIZE`)."""
    left = (image.width - IMAGE_SIZE[0]) // 2
    top = (image.height - IMAGE_SIZE[1]) // 2
    return image.crop((left, top, left + IMAGE_SIZE[0], top + IMAGE_SIZE[1]))


def _degrade(image: Image.Image, level: Level, rng: random.Random) -> Image.Image:
    """Empile les dégradations du niveau, toujours dans le même ordre (reproductibilité)."""
    if level.perspective > 0:
        width, height = image.size
        jitter = level.perspective
        corners = [
            (0.0, 0.0),
            (float(width), 0.0),
            (float(width), float(height)),
            (0.0, float(height)),
        ]
        warped = [
            (
                x + rng.uniform(-jitter, jitter) * width * 0.5,
                y + rng.uniform(-jitter, jitter) * height * 0.5,
            )
            for x, y in corners
        ]
        coefficients = _perspective_coefficients(warped, corners)
        image = image.transform(
            image.size, Image.Transform.PERSPECTIVE, coefficients, Image.Resampling.BILINEAR
        )

    if level.rotation_deg > 0:
        angle = rng.uniform(-level.rotation_deg, level.rotation_deg)
        image = image.rotate(
            angle, resample=Image.Resampling.BILINEAR, expand=False, fillcolor=(90, 95, 100)
        )

    if level.motion_blur_px > 1:
        image = _motion_blur(image, level.motion_blur_px, rng.uniform(-15.0, 15.0))

    exposure = rng.uniform(*level.exposure)
    if not math.isclose(exposure, 1.0, abs_tol=1e-3):
        array = np.asarray(image, dtype=np.float64) * exposure
        image = Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))

    image = _apply_noise(image, level.noise_sigma, rng)
    if level.index >= 4:
        # Une légère perte de netteté globale s'ajoute au flou directionnel : optique en
        # limite de résolution, JPEG de reportage.
        image = image.filter(ImageFilter.GaussianBlur(radius=0.6))
    return image


def generate_dataset(
    destination: str | Path, *, per_level: int = 60, seed: int = 20260821
) -> list[PlateSample]:
    """Génère le jeu et son manifeste JSON. Idempotent à graine égale.

    Renvoie la vérité terrain. Les images sont écrites en JPEG qualité 88 — même format et
    même compression que ce que traversera une photo réelle avant d'arriver à l'OCR.
    """
    target = Path(destination)
    target.mkdir(parents=True, exist_ok=True)
    entry_list = build_entry_list(seed)
    samples: list[PlateSample] = []
    for level in LEVELS:
        for index in range(per_level):
            image, sample = render_sample(index, level, seed, entry_list)
            image.save(target / sample.filename, format="JPEG", quality=88)
            samples.append(sample)
    (target / "manifest.json").write_text(
        json.dumps(
            {
                "seed": seed,
                "per_level": per_level,
                "entry_list": list(entry_list),
                "samples": [asdict(s) for s in samples],
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    return samples


def load_manifest(destination: str | Path) -> tuple[list[PlateSample], tuple[str, ...]] | None:
    """Relit un jeu déjà généré — évite de tout re-rendre entre deux exécutions de l'éval.

    Renvoie `(vérité terrain, table des engagements)`. La seconde est indispensable : sans
    elle, l'évaluation ne saurait pas distinguer « lecture fausse » de « numéro hors plateau ».
    """
    path = Path(destination) / "manifest.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "entry_list" not in payload:
        return None  # manifeste d'une version antérieure : on régénère plutôt que de deviner
    return (
        [PlateSample(**entry) for entry in payload["samples"]],
        tuple(payload["entry_list"]),
    )
