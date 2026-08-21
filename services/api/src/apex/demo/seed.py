"""Générateur de jeu de démo (§3-N.1 du plan, Décision N) — entièrement déterministe.

**Un seul appel produit le même état, bit-à-bit** (`random.Random(SEED)` + `Faker` seedé) :
catalogue (clients/écuries, circuits, pilotes, boîtiers) → 15 shootings sur 4 mois →
~60 engagements cohérents → ~8000 médias simulés → jusqu'à ~300 photos réelles ingérées par
le **vrai pipeline** si `demo-photos/` est peuplé (§ plan, « seul prérequis externe, non
bloquant pour le code »).

**Probité du jeu simulé** (§3-N.1, deux exigences non négociables) :
- `media.is_simulated = true` sur toute ligne issue de ce module — jamais mêlée
  silencieusement au réel, toujours interrogeable séparément (`GET /stats/*`, facette de
  recherche implicite via ce champ).
- Les distributions visent des chiffres défendables devant un professionnel du secteur :
  clichés par shooting, réglages corrélés (focale longue ⇒ ouverture plus fermée et ISO plus
  élevé, ISO qui grimpe en fin de session), taux de rafales, répartition des états de
  rattachement (§ `_ATTACHMENT_TARGETS` ci-dessous, reprise du plan telle quelle).

**Performance** (§3-N.1, objectif « < 15 s ») : toutes les tables volumineuses (`media`,
`media_series`, `media_engagement`, `media_ocr_candidate`) sont écrites en lots bornés
(`_BULK_CHUNK_SIZE`) via `INSERT … VALUES (...), (...), …` (l'« insertmanyvalues » de
SQLAlchemy 2.0, qui garantit l'ordre des lignes insérées) — pas de `COPY` binaire : écart
assumé au plan, mesuré et documenté dans `.agent-team/implementation.md`. Trois `UPDATE` en
lot (executemany, `bindparam`) posent `series_id`/le représentant de chaque rafale, jamais
une boucle par ligne. `media_search` est reconstruite en une seule fois par
`services/search_projection.py::project_media_search(session, None)` — la **même** requête
que la réindexation incrémentale (§ Décision N.1, « un unique `INSERT INTO media_search
SELECT …` »).

**Piège vérifié, coûteux** : `insert(Model)`/`update(Model)` (la classe ORM) exécutés via
`session.execute()` déclenchent, pour les modèles **sans relation** définie mais dont
l'identity map de la session porte déjà des milliers d'objets d'autres classes, un surcoût
d'ordres de grandeur par rapport à `insert(Model.__table__)`/`update(Model.__table__)` (Core
pur) — mesuré à ~45× plus lent sur `media_engagement` (4,6 s → 0,07 s par lot de 500 lignes)
dans ce générateur précisément. Toutes les écritures en lot de ce module passent donc par
`Model.__table__`, jamais par la classe ORM, dès qu'un volume significatif est en jeu.
"""

from __future__ import annotations

import colorsys
import io
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from faker import Faker
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import bindparam, func, insert, select, text, update
from sqlalchemy.orm import Session

from apex.config import settings
from apex.demo.accounts import ensure_demo_users
from apex.models.catalog import Camera, Circuit, Client, Driver, Team
from apex.models.media import Media, MediaEngagement, MediaSeries, PipelineEvent, UploadBatch
from apex.models.search import MediaOcrCandidate
from apex.models.setting import AppSetting
from apex.models.shooting import Engagement, Shooting, ShootingStaff
from apex.models.user import AppUser
from apex.pipeline.ocr.classify import (
    RESOLUTION_ABSTAIN,
    RESOLUTION_AUTO,
    RESOLUTION_NOT_ENGAGED,
    RESOLUTION_REVIEW,
)
from apex.pipeline.ocr.normalize import normalize_text
from apex.services.ocr_settings import ENGINE_VERSION_DEFAULT, OCR_HIGH_DEFAULT, OCR_LOW_DEFAULT
from apex.services.search_projection import project_media_search
from apex.services.storage import StorageClient, get_storage_client

SEED = 42
LAST_RESET_SETTING_KEY = "last_demo_reset"

# --- Volumétrie cible (§3-N.1) ------------------------------------------------------------
CLIENT_COUNT = 10
DRIVER_COUNT = 40
CAMERA_COUNT = 6
SHOOTING_COUNT = 15
TARGET_SIMULATED_MEDIA = 8000
SIM_THUMB_POOL_SIZE = 40
_BULK_CHUNK_SIZE = 500

# 8 circuits français réels (§3-N.1).
CIRCUITS: tuple[tuple[str, str], ...] = (
    ("Circuit des 24 Heures du Mans", "Le Mans"),
    ("Circuit de Nevers Magny-Cours", "Magny-Cours"),
    ("Circuit Paul Ricard", "Le Castellet"),
    ("Circuit de Dijon-Prenois", "Dijon"),
    ("Circuit Charade", "Clermont-Ferrand"),
    ("Circuit de Nogaro", "Nogaro"),
    ("Circuit de Pau-Arnos", "Pau"),
    ("Circuit d'Albi", "Albi"),
)

CLIENT_NAMES: tuple[str, ...] = (
    "Écurie Vallée Racing",
    "Chicane Motorsport",
    "Team Rafale Compétition",
    "Écurie du Plateau",
    "Apex Endurance",
    "Grand Est Racing",
    "Écurie Occitane",
    "Nord Motorsport",
    "Team Trajectoire",
    "Écurie Littoral Compétition",
)

LENS_POOL: tuple[str, ...] = (
    "70-200mm f/2.8",
    "100-400mm f/4.5-5.6",
    "24-70mm f/2.8",
    "300mm f/2.8",
    "150-600mm f/5-6.3",
)

CAPTION_TEMPLATES: tuple[str, ...] = (
    "Sortie de virage, plein angle",
    "Attaque en épingle",
    "Ligne droite, filé",
    "Freinage, dernier virage",
    "Départ de course",
    "Duel en virage",
    "Passage sous la passerelle",
    "Vibrations de chaleur, ligne droite",
)

QUARANTINE_SAMPLE: tuple[tuple[str, dict[str, Any]], ...] = (
    ("dimensions_out_of_range", {"width": 40, "height": 30}),
    ("exif_inconsistent", {"shot_at_exif": "1999-12-31T23:59:59"}),
    ("truncated_file", {"error": "fichier tronqué (simulation)"}),
    ("too_large", {"byte_size": 60_000_000, "max_upload_bytes": 26_214_400}),
)

# Distribution cible des états de rattachement (§3-N.1, reprise telle quelle du plan) :
# ~78% engagement_attached (72% pipeline_ocr / 28% human), ~12% shooting_attached,
# ~5% pending_review, ~3% unattached, ~2% inconsistent, ~1% quarantined.
_ATTACHMENT_TARGETS: tuple[tuple[str, float], ...] = (
    ("engagement_attached", 0.78),
    ("shooting_attached", 0.12),
    ("pending_review", 0.05),
    ("unattached", 0.03),
    ("inconsistent", 0.02),
)
_QUARANTINE_RATE = 0.01  # tiré indépendamment, en plus des buckets ci-dessus (§3-N.1).

# --- Revue J2 (🟠 n°9) : candidats bruts sur tout le catalogue, pas seulement 5,6% -----
#
# Avant ce correctif, seuls les bacs `pending_review`/`inconsistent` recevaient un candidat
# OCR persisté — `engagement_attached` posait directement une ligne `media_engagement` sans
# jamais passer par `media_ocr_candidate`. Conséquence mesurée : `GET /settings/ocr`
# affichait `auto: 0` quand `GET /stats/auto-attach-rate` affichait `auto_ocr: 4786` (deux
# écrans contradictoires devant un prospect), et `PUT /settings/ocr` ne pouvait redistribuer
# que les 479 médias déjà pourvus d'un candidat (5,6 % du jeu de 8 472). Deux ajouts,
# tous deux au-dessus/en dessous des seuils par défaut (`services/ocr_settings.py`) pour
# rester cohérents avec `OCR_HIGH_DEFAULT`/`OCR_LOW_DEFAULT` sans les dupliquer :
# - un candidat `auto` pour chaque média `engagement_attached` dont le rattachement vient
#   du pipeline OCR (`attachment_source == "pipeline_ocr"`, ~72 % du bac) ;
# - un candidat `abstain` pour une part des médias non rattachés à un engagement
#   (`shooting_attached`/`unattached`) — une hypothèse basse confiance, cohérente avec
#   « le modèle a bien lu quelque chose, pas assez sûr pour rattacher ».
#
# **Suite, intégration live J2 finale** : ce correctif a *aussi* introduit `group_engagement_ids`
# pour le bac `pending_review` (nécessaire pour donner à son candidat le bon `engagement_id`
# suggéré, § `_plan_shooting_media`) — mais la boucle de matérialisation des rattachements
# (plus bas, § `_create_simulated_media`) ne distinguait pas les bacs et posait une ligne
# `media_engagement` pour `pending_review` aussi, alors que ce bac n'en a, par construction,
# encore aucun (seules `auto`/`accepted` en matérialisent un en production, §
# `classify.ATTACHING_RESOLUTIONS`). Nouvelle contradiction du même type que celle
# ci-dessus, cette fois entre `auto_ocr` (`GET /stats/auto-attach-rate`, compte par `EXISTS
# media_engagement`) et `distribution.auto`/la facette `engagement_attached` de `/search` —
# corrigée en restreignant cette matérialisation au seul bac `engagement_attached`.
_LOW_CONFIDENCE_SAMPLE_RATE = 0.45

# TRUNCATE (§3-N.2) — la table `job` n'y figure jamais (un job en cours pourrait s'y trouver,
# purgée séparément de ses entrées `done` de plus de 24 h par le futur handler `demo_reset`).
# `app_setting` n'y figure pas non plus : elle porte des réglages qui survivent au jeu de
# démo lui-même (seuils OCR, `last_demo_reset`), jamais réinitialisés par un reset.
#
# **Écart corrigé au plan** : la liste TRUNCATE du §3-N.2 omet `circuit` — reproduit en
# conditions réelles (`tests/demo/test_seed.py`) : un second `reset=True` échoue en
# `UniqueViolation` sur `circuit.name`, les 8 circuits réels du catalogue (§3-N.1) n'étant
# jamais effacés. Ajouté ici ; à signaler en revue comme correctif du plan, pas un désaccord.
_RESET_TABLES: tuple[str, ...] = (
    "media",
    "media_search",
    "media_engagement",
    "media_ocr_candidate",
    "media_series",
    "upload_batch",
    "pipeline_event",
    "engagement",
    "shooting_staff",
    "shooting",
    "collection",
    "collection_item",
    "share_link",
    "client_selection",
    "selection_item",
    "delivery",
    "quote",
    "invoice",
    "invoice_line",
    "client",
    "driver",
    "team",
    "camera",
    "circuit",
    "app_user",
)


class PartialDemoCatalogError(RuntimeError):
    """Second filet du correctif heartbeat (revue J2, 🔴 n°2).

    Avant ce correctif, un `POST /demo/seed` interrompu entre le commit prématuré causé par
    `ctx.heartbeat()` et la fin de `run_seed` laissait `client`/`media` peuplés sans que
    `last_demo_reset` soit jamais écrit — `run_seed(reset=False)` rejoué ensuite voyait
    `catalog_exists=True` et renvoyait silencieusement `ran=False` : la démo restait cassée
    en permanence (`media_search` vide, `GET /search` à 0), job vert, aucune erreur. Même la
    connexion dédiée du heartbeat ne protège pas contre un worker tué par un autre mécanisme
    en cours de route — ce filet est indépendant de la cause de l'interruption.
    """


def _catalog_is_partial(session: Session) -> bool:
    """`client` peuplé mais `last_demo_reset` absent : un run précédent a démarré sans
    aller à son terme. Une seule requête, cf. `PartialDemoCatalogError`.
    """
    catalog_exists = session.execute(select(func.count()).select_from(Client)).scalar_one() > 0
    if not catalog_exists:
        return False
    last_reset = session.execute(
        select(AppSetting.key).where(AppSetting.key == LAST_RESET_SETTING_KEY)
    ).scalar_one_or_none()
    return last_reset is None


@dataclass(slots=True)
class SeedResult:
    reset: bool
    ran: bool
    clients: int = 0
    circuits: int = 0
    drivers: int = 0
    teams: int = 0
    cameras: int = 0
    shootings: int = 0
    engagements: int = 0
    simulated_media: int = 0
    real_media: int = 0
    real_photos_skipped_reason: str | None = None
    duration_ms: int = 0
    attachment_status_counts: dict[str, int] = field(default_factory=dict)


def _truncate_demo_tables(session: Session) -> None:
    names = ", ".join(f'"{t}"' for t in _RESET_TABLES)
    session.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))


def _write_last_reset(session: Session) -> None:
    now = datetime.now(UTC)
    row = session.execute(
        select(AppSetting).where(AppSetting.key == LAST_RESET_SETTING_KEY)
    ).scalar_one_or_none()
    if row is None:
        session.add(AppSetting(key=LAST_RESET_SETTING_KEY, value={"value": now.isoformat()}))
    else:
        row.value = {"value": now.isoformat()}
        row.updated_at = now


# --- Catalogue -----------------------------------------------------------------------


def _create_catalog(
    session: Session, rng: random.Random, faker: Faker
) -> tuple[list[Client], list[Circuit], list[Driver], list[Team], list[Camera], AppUser, AppUser]:
    ensure_demo_users(session)
    session.flush()
    owner = session.execute(select(AppUser).where(AppUser.role == "owner")).scalar_one()
    photographer = session.execute(
        select(AppUser).where(AppUser.role == "photographer")
    ).scalar_one()

    clients = [
        Client(
            name=name,
            kind="team",
            contact_name=faker.name(),
            contact_email=faker.company_email(),
            phone=faker.phone_number(),
        )
        for name in CLIENT_NAMES
    ]
    session.add_all(clients)

    circuits = [Circuit(name=name, city=city, country="France") for name, city in CIRCUITS]
    session.add_all(circuits)

    drivers = [Driver(full_name=faker.name(), nationality="FR") for _ in range(DRIVER_COUNT)]
    session.add_all(drivers)
    session.flush()

    teams = [Team(name=f"{client.name} — Équipe course", client_id=client.id) for client in clients]
    session.add_all(teams)

    cameras = [
        Camera(
            exif_serial=f"SIM-{i:04d}",
            make=rng.choice(["Canon", "Nikon", "Sony"]),
            model=rng.choice(["EOS R3", "Z9", "A9 III", "EOS 1D X Mark III"]),
            owner_user_id=photographer.id,
            clock_offset_seconds=0,
            timezone="Europe/Paris",
        )
        for i in range(CAMERA_COUNT)
    ]
    session.add_all(cameras)
    session.flush()

    return clients, circuits, drivers, teams, cameras, owner, photographer


# --- Shootings & engagements -----------------------------------------------------------


def _create_shootings(
    session: Session,
    rng: random.Random,
    clients: list[Client],
    circuits: list[Circuit],
    photographer: AppUser,
) -> list[Shooting]:
    """15 shootings répartis sur 4 mois, 2 sessions/jour plausibles (§3-N.1)."""
    start_window = datetime.now(UTC) - timedelta(days=120)
    shootings: list[Shooting] = []
    for i in range(SHOOTING_COUNT):
        day_offset = int(120 * i / SHOOTING_COUNT) + rng.randint(0, 3)
        day = start_window + timedelta(days=day_offset)
        session_hour = rng.choice([9, 14])  # matin ou après-midi (§3-N.1)
        starts_at = day.replace(hour=session_hour, minute=0, second=0, microsecond=0)
        duration = timedelta(hours=rng.uniform(1.5, 3.0))
        circuit = circuits[i % len(circuits)]
        client = rng.choice(clients)
        status = "done" if starts_at < datetime.now(UTC) else "planned"
        shooting = Shooting(
            client_id=client.id,
            circuit_id=circuit.id,
            title=f"{circuit.city} — {starts_at:%d %B %Y}",
            starts_at=starts_at,
            ends_at=starts_at + duration,
            status=status,
        )
        session.add(shooting)
        shootings.append(shooting)
    session.flush()

    for shooting in shootings:
        session.add(ShootingStaff(shooting_id=shooting.id, user_id=photographer.id, role="lead"))
    session.flush()
    return shootings


def _create_engagements(
    session: Session,
    rng: random.Random,
    shootings: list[Shooting],
    drivers: list[Driver],
    teams: list[Team],
    clients: list[Client],
) -> dict[int, list[Engagement]]:
    """~60 engagements (§3-N.1), numéros uniques par shooting (`UniqueConstraint`)."""
    by_shooting: dict[int, list[Engagement]] = {}
    for shooting in shootings:
        count = rng.randint(3, 5)
        numbers = rng.sample(range(1, 100), count)
        engagements = []
        for number in numbers:
            driver = rng.choice(drivers)
            team = rng.choice(teams)
            engagement = Engagement(
                shooting_id=shooting.id,
                car_number=str(number),
                driver_id=driver.id,
                team_id=team.id,
                client_id=team.client_id or rng.choice(clients).id,
                car_model=rng.choice(["GT3", "GT4", "Formule 4", "Proto LMP3", "Rallye R5"]),
            )
            session.add(engagement)
            engagements.append(engagement)
        by_shooting[shooting.id] = engagements
    session.flush()
    return by_shooting


# --- Vignettes procédurales du pool simulé (§3-N.1) -----------------------------------


def _build_sim_thumbnail(index: int) -> bytes:
    """Dégradé + numéro + bandeau « SIMULÉ » — jamais un cliché réel (probité du jeu)."""
    width, height = 320, 213
    hue = (index * 37) % 360
    top = _hsv_to_rgb(hue, 0.55, 0.85)
    bottom = _hsv_to_rgb(hue, 0.65, 0.35)
    # Dégradé vectorisé (numpy) plutôt que `putpixel` par pixel (§3-N.1, performance
    # mesurée) : ~2,7M appels `putpixel` pour 40 vignettes coûtaient à eux seuls plusieurs
    # secondes du budget « < 15 s » — un array construit en une fois, converti en `Image`,
    # est immédiat.
    t = np.linspace(0.0, 1.0, height, dtype=np.float64).reshape(height, 1, 1)
    top_arr = np.array(top, dtype=np.float64).reshape(1, 1, 3)
    bottom_arr = np.array(bottom, dtype=np.float64).reshape(1, 1, 3)
    gradient = (top_arr * (1 - t) + bottom_arr * t).astype(np.uint8)
    gradient = np.broadcast_to(gradient, (height, width, 3))
    img = Image.fromarray(np.ascontiguousarray(gradient), mode="RGB")
    draw = ImageDraw.Draw(img)
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    small_font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 40)
        small_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
        small_font = font
    draw.text((width / 2, height / 2 - 20), f"#{index}", font=font, fill="white", anchor="mm")
    draw.rectangle([(0, height - 24), (width, height)], fill=(0, 0, 0, 180))
    draw.text((width / 2, height - 12), "SIMULÉ", font=small_font, fill="white", anchor="mm")
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=70)
    return buf.getvalue()


def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(h / 360, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def _ensure_sim_thumbnail_pool(storage: StorageClient) -> list[str]:
    """Uploade le pool ~40 vignettes **une seule fois** (§3-N.1) — le stockage objet n'est
    donc jamais touché par un reset (les clés `sim/{i}.webp` sont fixes et réutilisées).
    """
    keys = [f"sim/{i}.webp" for i in range(SIM_THUMB_POOL_SIZE)]
    for i, key in enumerate(keys):
        if not storage.exists(key):
            storage.put_bytes(key, _build_sim_thumbnail(i), content_type="image/webp")
    return keys


# --- Réglages corrélés (§3-N.1) ---------------------------------------------------------


def _correlated_settings(rng: random.Random, progress: float) -> tuple[float, float, str, float]:
    """`(iso, aperture, shutter_label, focal_length)` — focale longue ⇒ ouverture plus
    fermée et ISO plus élevé ; l'ISO grimpe en fin de session (`progress` ∈ [0, 1]).
    """
    focal_length = rng.choice([24, 35, 70, 135, 200, 300, 400])
    aperture = round(2.8 + (focal_length / 400) * 5.2 + rng.uniform(-0.3, 0.3), 1)
    base_iso = 200 + (focal_length / 400) * 800
    iso = base_iso * (1 + 1.4 * progress) * rng.uniform(0.85, 1.15)
    iso = min(12800.0, max(100.0, round(iso / 100) * 100))
    shutter_denominator = rng.choice([250, 320, 400, 500, 640, 800, 1000])
    return iso, max(1.4, aperture), f"1/{shutter_denominator}", float(focal_length)


# --- Génération des médias simulés, par shooting ----------------------------------------


@dataclass(slots=True)
class _PlannedMedia:
    row: dict[str, Any]
    bucket: str
    engagement_ids: list[int]
    ocr_candidate: dict[str, Any] | None
    group_key: int | None  # index de groupe de rafale, `None` si isolé
    sharpness: float


def _pick_bucket(rng: random.Random) -> str:
    if rng.random() < _QUARANTINE_RATE:
        return "quarantined"
    roll = rng.random()
    cumulative = 0.0
    for bucket, weight in _ATTACHMENT_TARGETS:
        cumulative += weight
        if roll <= cumulative:
            return bucket
    return _ATTACHMENT_TARGETS[-1][0]


def _plan_shooting_media(
    rng: random.Random,
    faker: Faker,
    shooting: Shooting,
    cameras: list[Camera],
    engagements: list[Engagement],
    photographer_id: int,
    thumb_keys: list[str],
    media_count: int,
    group_counter: list[int],
) -> list[_PlannedMedia]:
    planned: list[_PlannedMedia] = []
    window = (shooting.ends_at - shooting.starts_at).total_seconds()
    engaged_numbers = {e.car_number for e in engagements}

    remaining = media_count
    while remaining > 0:
        is_burst = rng.random() >= 0.15 and remaining >= 3
        group_size = min(rng.randint(3, 8), remaining) if is_burst else 1
        remaining -= group_size

        camera = rng.choice(cameras)
        offset_seconds = rng.uniform(0, max(window - group_size * 0.25, 1))
        progress = offset_seconds / window if window else 0.0
        bucket = _pick_bucket(rng)
        if bucket in ("engagement_attached", "pending_review", "inconsistent") and not engagements:
            # Aucun engagement à ce shooting (cas limite : plateau très réduit) — ces trois
            # bacs n'ont de sens que rapportés à une table d'engagements (AGENTS.md,
            # invariant « un numéro seul n'a aucun sens hors de son événement »).
            bucket = "shooting_attached"
        group_key: int | None = None
        if group_size >= 2:
            group_counter[0] += 1
            group_key = group_counter[0]

        group_engagement_ids: list[int] = []
        not_engaged_number = None
        if bucket in ("engagement_attached", "pending_review") and engagements:
            k = 2 if rng.random() < 0.10 else 1
            group_engagement_ids = [e.id for e in rng.sample(engagements, min(k, len(engagements)))]
        elif bucket == "inconsistent":
            candidate_number = str(rng.randint(1, 199))
            tries = 0
            while candidate_number in engaged_numbers and tries < 10:
                candidate_number = str(rng.randint(1, 199))
                tries += 1
            not_engaged_number = candidate_number

        sharpness_base = rng.uniform(40.0, 260.0)
        for i in range(group_size):
            shot_at = shooting.starts_at + timedelta(seconds=offset_seconds + i * 0.22)
            iso, aperture, shutter_label, focal_length = _correlated_settings(rng, progress)
            sharpness = sharpness_base + rng.uniform(-15.0, 15.0)
            thumb_key = rng.choice(thumb_keys)

            attachment_status = bucket if bucket != "quarantined" else "unattached"
            attachment_source: str | None = None
            quarantine_reason = None
            quarantine_detail = None
            shooting_id: int | None = shooting.id
            caption = rng.choice(CAPTION_TEMPLATES) if rng.random() < 0.35 else None
            keywords = [shooting.title.split(" — ")[0]] if caption else None

            ocr_candidate: dict[str, Any] | None = None
            if bucket == "quarantined":
                quarantine_reason, quarantine_detail = rng.choice(QUARANTINE_SAMPLE)
                shooting_id = None
            elif bucket == "unattached":
                shooting_id = None
            elif bucket == "shooting_attached":
                attachment_source = "pipeline_time"
            elif bucket == "engagement_attached":
                attachment_source = "human" if rng.random() >= 0.72 else "pipeline_ocr"
            elif bucket == "pending_review":
                # Garanti non vide : le repli ci-dessus bascule ce bac en `shooting_attached`
                # dès que le shooting n'a aucun engagement.
                attachment_source = None
                target_engagement_id = group_engagement_ids[0]
                number = next(e.car_number for e in engagements if e.id == target_engagement_id)
                ocr_candidate = {
                    "raw_text": number,
                    "normalized_number": normalize_text(number).number,
                    "confidence": round(rng.uniform(0.46, 0.79), 4),
                    "resolution": RESOLUTION_REVIEW,
                    "engagement_id": target_engagement_id,
                }
            elif bucket == "inconsistent":
                attachment_source = None
                ocr_candidate = {
                    "raw_text": not_engaged_number or "0",
                    "normalized_number": not_engaged_number,
                    "confidence": round(rng.uniform(0.5, 0.95), 4),
                    "resolution": RESOLUTION_NOT_ENGAGED,
                    "engagement_id": None,
                }

            # 🟠 n°9 — cf. commentaire de `_LOW_CONFIDENCE_SAMPLE_RATE` : candidats bruts sur
            # les deux bacs qui n'en recevaient jamais aucun.
            if bucket == "engagement_attached" and attachment_source == "pipeline_ocr":
                # Garanti non vide : ce bac n'existe que si `engagements` est non vide (repli
                # plus haut), donc `group_engagement_ids` a été peuplé pour ce cas.
                target_engagement_id = group_engagement_ids[0]
                number = next(e.car_number for e in engagements if e.id == target_engagement_id)
                ocr_candidate = {
                    "raw_text": number,
                    "normalized_number": normalize_text(number).number,
                    "confidence": round(rng.uniform(OCR_HIGH_DEFAULT + 0.01, 0.99), 4),
                    "resolution": RESOLUTION_AUTO,
                    "engagement_id": target_engagement_id,
                }
            elif (
                bucket in ("shooting_attached", "unattached")
                and engagements
                and rng.random() < _LOW_CONFIDENCE_SAMPLE_RATE
            ):
                guess = rng.choice(engagements)
                ocr_candidate = {
                    "raw_text": guess.car_number,
                    "normalized_number": normalize_text(guess.car_number).number,
                    "confidence": round(rng.uniform(0.05, OCR_LOW_DEFAULT - 0.01), 4),
                    "resolution": RESOLUTION_ABSTAIN,
                    "engagement_id": guess.id,
                }

            row: dict[str, Any] = {
                "uploaded_by": photographer_id,
                "idempotency_key": f"sim-{faker.uuid4()}",
                "original_filename": f"DSC_{rng.randint(1000, 9999)}.jpg",
                "byte_size": rng.randint(6_000_000, 24_000_000),
                "mime": "image/jpeg",
                "width": 6000,
                "height": 4000,
                # Pas de HD pour un média simulé (§3-N.1 : un seul pool ~40 vignettes,
                # jamais de fichier « grand format ») — `GET /media/{id}/file/hd` répond
                # `404 variant_not_ready`, comportement déjà géré par `routers/media.py`.
                "storage_key_hd": None,
                "storage_key_preview": thumb_key,
                "storage_key_thumb": thumb_key,
                "shot_at_exif": shot_at.replace(tzinfo=None),
                "shot_at": shot_at,
                "camera_id": camera.id,
                "lens_model": rng.choice(LENS_POOL),
                "iso": int(iso),
                "shutter_speed_label": shutter_label,
                "shutter_speed_sec": 1 / int(shutter_label.split("/")[1]),
                "aperture": aperture,
                "focal_length": focal_length,
                "phash": rng.getrandbits(62),
                "sharpness": round(sharpness, 4),
                "ingest_status": "quarantined" if bucket == "quarantined" else "ingested",
                "quarantine_reason": quarantine_reason,
                "quarantine_detail": quarantine_detail,
                "attachment_status": attachment_status,
                "attachment_source": attachment_source,
                "attachment_detail": (
                    {"reason": "no_matching_window"} if bucket == "unattached" else None
                ),
                "shooting_id": shooting_id,
                "is_simulated": True,
                "caption": caption,
                "keywords": keywords,
            }
            planned.append(
                _PlannedMedia(
                    row=row,
                    bucket=bucket,
                    engagement_ids=list(group_engagement_ids),
                    ocr_candidate=ocr_candidate,
                    group_key=group_key,
                    sharpness=sharpness,
                )
            )
    return planned


def _create_simulated_media(
    session: Session,
    rng: random.Random,
    faker: Faker,
    shootings: list[Shooting],
    cameras: list[Camera],
    engagements_by_shooting: dict[int, list[Engagement]],
    photographer: AppUser,
    thumb_keys: list[str],
) -> tuple[int, dict[str, int]]:
    batch = UploadBatch(
        created_by=photographer.id,
        expected_count=TARGET_SIMULATED_MEDIA,
        received_count=0,
        status="closed",
    )
    session.add(batch)
    session.flush()

    per_shooting = TARGET_SIMULATED_MEDIA // SHOOTING_COUNT
    group_counter = [0]
    all_planned: list[_PlannedMedia] = []
    for shooting in shootings:
        count = max(50, int(rng.gauss(per_shooting, per_shooting * 0.25)))
        all_planned.extend(
            _plan_shooting_media(
                rng,
                faker,
                shooting,
                cameras,
                engagements_by_shooting.get(shooting.id, []),
                photographer.id,
                thumb_keys,
                count,
                group_counter,
            )
        )

    for planned in all_planned:
        planned.row["batch_id"] = batch.id

    # --- Insertion en lots bornés (§ docstring de module : écart assumé à `COPY`) -------
    inserted_ids: list[int] = []
    for start in range(0, len(all_planned), _BULK_CHUNK_SIZE):
        chunk = all_planned[start : start + _BULK_CHUNK_SIZE]
        result = session.execute(
            insert(Media.__table__).returning(Media.__table__.c.id),  # type: ignore[arg-type]
            [p.row for p in chunk],
        )
        inserted_ids.extend(int(r) for r in result.scalars().all())
    session.flush()

    for planned, media_id in zip(all_planned, inserted_ids, strict=True):
        planned.row["id"] = media_id

    # --- Séries (rafales) — construites directement, sans repasser par pipeline/series.py
    #
    # **Correctif de performance** (§3-N.1, objectif « < 15 s » mesuré) : la première version
    # faisait un `session.add()` + `flush()` **par groupe** (~1450 groupes sur 8000 médias),
    # plus deux `UPDATE` séparés chacun — near 4400 aller-retours réseau bloquants, mesurés à
    # 89 s à eux seuls (`cProfile`, dominé par `select.select` = attente réseau). Toute la
    # section est désormais **groupée** : un seul `INSERT … RETURNING` pour les séries, une
    # seule passe d'`UPDATE` en lot (executemany) pour `series_id`/représentant — même
    # principe que l'insertion de `media` plus haut. Descend sous la seconde.
    groups: dict[int, list[tuple[_PlannedMedia, int]]] = {}
    for planned, media_id in zip(all_planned, inserted_ids, strict=True):
        if planned.group_key is not None:
            groups.setdefault(planned.group_key, []).append((planned, media_id))

    series_rows: list[dict[str, Any]] = []
    series_members: list[list[tuple[_PlannedMedia, int]]] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        group_shooting_id = members[0][0].row["shooting_id"]
        if group_shooting_id is None:
            continue  # une rafale n'a de sens que rattachée à un shooting (§3-G.3)
        shot_ats = [m.row["shot_at"] for m, _ in members]
        series_rows.append(
            {
                "shooting_id": group_shooting_id,
                "camera_id": members[0][0].row["camera_id"],
                "started_at": min(shot_ats),
                "ended_at": max(shot_ats),
                "member_count": len(members),
            }
        )
        series_members.append(members)

    series_ids: list[int] = []
    for start in range(0, len(series_rows), _BULK_CHUNK_SIZE):
        series_chunk = series_rows[start : start + _BULK_CHUNK_SIZE]
        result = session.execute(
            insert(MediaSeries.__table__).returning(MediaSeries.__table__.c.id),  # type: ignore[arg-type]
            series_chunk,
        )
        series_ids.extend(int(r) for r in result.scalars().all())
    session.flush()

    # Trois passes **en lot** (executemany, un seul aller-retour logique chacune — pas un
    # par série ni par média) : `series_id` de tous les membres, `is_series_representative`
    # du seul représentant, `representative_media_id` de la série elle-même.
    media_series_id_updates: list[dict[str, Any]] = []
    media_representative_updates: list[dict[str, Any]] = []
    series_representative_updates: list[dict[str, Any]] = []
    for series_id, members in zip(series_ids, series_members, strict=True):
        for _planned, media_id in members:
            media_series_id_updates.append({"_media_id": media_id, "_series_id": series_id})
        representative = max(members, key=lambda pair: pair[0].sharpness)
        media_representative_updates.append({"_media_id": representative[1]})
        series_representative_updates.append(
            {"_series_id": series_id, "_representative_media_id": representative[1]}
        )

    if media_series_id_updates:
        # `update(Model.__table__)` (Core, pas `update(Model)`) : le formulaire ORM
        # applique une heuristique de « bulk UPDATE by primary key » qui exige que la clé
        # primaire porte son propre nom de colonne dans les paramètres — incompatible avec
        # des noms de bind personnalisés (`InvalidRequestError`, reproduit en conditions
        # réelles). Ces lignes viennent d'être insérées en Core pur, jamais chargées dans
        # l'identity map : un simple `UPDATE` en lot suffit, sans aucune synchronisation ORM.
        session.execute(
            update(Media.__table__)  # type: ignore[arg-type]
            .where(Media.id == bindparam("_media_id"))
            .values(series_id=bindparam("_series_id")),
            media_series_id_updates,
        )
        session.execute(
            update(Media.__table__)  # type: ignore[arg-type]
            .where(Media.id == bindparam("_media_id"))
            .values(is_series_representative=True),
            media_representative_updates,
        )
        session.execute(
            update(MediaSeries.__table__)  # type: ignore[arg-type]
            .where(MediaSeries.id == bindparam("_series_id"))
            .values(representative_media_id=bindparam("_representative_media_id")),
            series_representative_updates,
        )
        session.flush()

    # --- Rattachements (media_engagement) + candidats OCR (bacs review/inconsistent) ----
    engagement_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for planned, media_id in zip(all_planned, inserted_ids, strict=True):
        counts[planned.bucket] = counts.get(planned.bucket, 0) + 1
        # `group_engagement_ids` (→ `planned.engagement_ids`) est peuplé pour deux bacs
        # (§ `_plan_shooting_media` : `engagement_attached` ET `pending_review`, ce dernier
        # pour connaître l'engagement visé par son candidat OCR ci-dessous). Seul le premier
        # doit matérialiser une ligne `media_engagement` : `pending_review` n'a, par
        # construction, encore **aucun** rattachement — c'est même le sens du bac (file de
        # validation humaine, § tableau des issues de `pipeline/ocr/classify.py`, dont seules
        # `auto`/`accepted` — `ATTACHING_RESOLUTIONS` — matérialisent un lien en production).
        # Avant ce correctif, une ligne `media_engagement` fictive (`source='pipeline_ocr'`,
        # `created_by=None`) était posée ici pour `pending_review` aussi, gonflant
        # artificiellement `GET /stats/auto-attach-rate.auto_ocr` (qui compte par `EXISTS
        # media_engagement`) de la taille de la file de validation — jusqu'à ce qu'une
        # première projection (`PUT /settings/ocr`, `POST /jobs/tick`) la retire, donnant
        # l'illusion d'une baisse du rattachement automatique. § doc de
        # `routers/stats.py::auto_attach_rate` et `tests/demo/test_seed.py` pour le
        # verrou de non-régression.
        if planned.bucket == "engagement_attached":
            for engagement_id in planned.engagement_ids:
                source = planned.row.get("attachment_source") or "pipeline_ocr"
                # 🟠 n°9 : quand ce rattachement est justifié par le candidat OCR généré
                # ci-dessus pour ce média (même `engagement_id`), reprendre **sa** confiance —
                # c'est exactement ce que fait `classify._materialise_links` en production
                # (`confidence=float(candidate.confidence)`). Un second rattachement de la
                # même rafale multi-voiture (k=2, sans candidat propre) retombe sur l'ancien
                # tirage indépendant.
                candidate_confidence = (
                    planned.ocr_candidate["confidence"]
                    if planned.ocr_candidate is not None
                    and planned.ocr_candidate.get("engagement_id") == engagement_id
                    else None
                )
                engagement_rows.append(
                    {
                        "media_id": media_id,
                        "engagement_id": engagement_id,
                        "source": "human" if source == "human" else "ocr",
                        "confidence": (
                            None
                            if source == "human"
                            else candidate_confidence or round(rng.uniform(0.85, 0.99), 4)
                        ),
                        "created_by": photographer.id if source == "human" else None,
                    }
                )
        if planned.ocr_candidate is not None:
            candidate_rows.append(
                {
                    "media_id": media_id,
                    "raw_text": planned.ocr_candidate["raw_text"],
                    "normalized_number": planned.ocr_candidate["normalized_number"],
                    "confidence": planned.ocr_candidate["confidence"],
                    "bbox": {"x": 0.4, "y": 0.5, "w": 0.12, "h": 0.08},
                    "engine_version": ENGINE_VERSION_DEFAULT,
                    "resolution": planned.ocr_candidate["resolution"],
                    "engagement_id": planned.ocr_candidate["engagement_id"],
                }
            )

    for start in range(0, len(engagement_rows), _BULK_CHUNK_SIZE):
        session.execute(
            insert(MediaEngagement.__table__),  # type: ignore[arg-type]
            engagement_rows[start : start + _BULK_CHUNK_SIZE],
        )
    for start in range(0, len(candidate_rows), _BULK_CHUNK_SIZE):
        session.execute(
            insert(MediaOcrCandidate.__table__),  # type: ignore[arg-type]
            candidate_rows[start : start + _BULK_CHUNK_SIZE],
        )
    session.flush()

    batch.received_count = len(inserted_ids)
    return len(inserted_ids), counts


# --- Photos réelles (best-effort, §5 du brief : « seul prérequis externe, non bloquant ») --


def _ingest_real_photos(
    session: Session,
    storage: StorageClient,
    photographer: AppUser,
    shootings: list[Shooting],
    *,
    heartbeat: Callable[[], None],
) -> tuple[int, str | None]:
    real_dir = Path(settings.real_photos_dir)
    if not real_dir.is_dir():
        return 0, f"« {real_dir} » absent — jeu synthétique uniquement (prérequis non bloquant)."
    files = sorted(p for p in real_dir.glob("*.jpg"))[:300]
    if not files:
        return 0, f"« {real_dir} » vide — jeu synthétique uniquement (prérequis non bloquant)."

    from apex.pipeline import attach_time
    from apex.pipeline.ingest import run_ingest_media
    from apex.queue.enqueue import enqueue
    from apex.services.storage import incoming_key

    batch = UploadBatch(created_by=photographer.id, expected_count=len(files), status="processing")
    session.add(batch)
    session.flush()

    ingested = 0
    for i, path in enumerate(files):
        # § worker-queue.instructions.md : « les handlers longs appellent `ctx.heartbeat()`
        # régulièrement ». Non déclenché tant que `demo-photos/` est vide (prérequis non
        # sourcé), mais borné par photo une fois peuplé — jusqu'à 300 passages complets du
        # pipeline réel, potentiellement plusieurs minutes.
        heartbeat()
        data = path.read_bytes()
        idempotency_key = f"real-{i:04d}"
        storage.put_bytes(incoming_key(batch.id, idempotency_key), data, content_type="image/jpeg")
        media = Media(
            batch_id=batch.id,
            uploaded_by=photographer.id,
            idempotency_key=idempotency_key,
            original_filename=path.name,
            byte_size=len(data),
            ingest_status="uploaded",
            is_simulated=False,
        )
        session.add(media)
        session.flush()
        run_ingest_media(session, media, storage, job_id=None, studio_name="Studio Chicane")

        # Photos réelles : leur date de prise de vue authentique (des courses réellement
        # disputées — parfois des années plus tôt — préservée telle quelle dans
        # `shot_at_exif`) ne tombe quasiment jamais dans la fenêtre d'un shooting fictif
        # généré relativement à « maintenant » (§3-N.1) : « Studio Chicane » n'existait pas
        # au moment de ces prises de vue. Sans correctif, `attach_media_by_time` (ci-dessus,
        # dans `run_ingest_media`) laisse donc systématiquement ces médias dans le bac
        # « à rattacher », et `queue/handlers/ocr_media.py` les ignore ensuite
        # (`shooting_id is None` → skip `no_shooting`) : le jeu réel ne démontrerait jamais
        # le cœur du jalon J2 (OCR + recoupement engagements), alors que son sourcing cible
        # précisément des numéros de course lisibles dans ce but (§ décision documentée dans
        # `.agent-team/implementation.md`, section Backend — signalé pour arbitrage).
        #
        # Correctif volontairement minimal, appliqué seulement quand le rattachement
        # naturel a échoué : répartition round-robin sur les shootings du jeu (déjà générés
        # à cet instant), en ne touchant que `media.shot_at` — jamais `shot_at_exif`, qui
        # reste la date réellement lue dans le fichier (§ docstring d'`ingest.py`,
        # « shot_at_exif reste distinct »). `attach_media_by_time` rattache alors la photo
        # par son mécanisme habituel : `attachment_source='pipeline_time'` reste donc
        # littéralement vrai, pas une valeur inventée hors de l'énumération fermée.
        if media.ingest_status == "ingested" and media.shooting_id is None and shootings:
            shooting = shootings[i % len(shootings)]
            duration_seconds = (shooting.ends_at - shooting.starts_at).total_seconds()
            offset_seconds = min((i * 47) % 3000, max(duration_seconds - 1, 0))
            media.shot_at = shooting.starts_at + timedelta(seconds=offset_seconds)
            attach_time.attach_media_by_time(session, media)
            session.add(
                PipelineEvent(
                    media_id=media.id,
                    batch_id=batch.id,
                    job_id=None,
                    step="attach_time_demo_reassign",
                    status="ok" if media.shooting_id is not None else "skipped",
                    duration_ms=0,
                    message=(
                        f"photo réelle réassignée au shooting démo #{shooting.id} "
                        "(EXIF authentique hors plage — § implementation.md)"
                    ),
                )
            )

        # §3-F.1, étape 9 (J2) : même règle que `queue/handlers/ingest_media.py` — seule
        # une photo *réellement* rattachée à un shooting est envoyée à l'OCR. Contrairement
        # aux médias simulés (candidats `media_ocr_candidate` fabriqués directement, §3-N.1
        # — aucun besoin d'inférence sur une image générée), une photo réelle doit
        # traverser le **vrai** moteur RapidOCR : c'est tout l'intérêt de ce jeu. `run_seed`
        # ne drainant pas la file lui-même, ce job attend le prochain tick du worker
        # (`apex.cli worker --once`/`--loop`) — voir la vérification de bout en bout dans
        # `.agent-team/implementation.md`.
        if (
            media.ingest_status == "ingested"
            and media.duplicate_of_media_id is None
            and media.shooting_id is not None
        ):
            enqueue(
                session,
                "ocr_media",
                {"media_id": media.id},
                dedupe_key=f"ocr:{media.id}",
                priority=110,
            )

        project_media_search(session, [media.id])
        ingested += 1
    batch.received_count = ingested
    batch.status = "closed"
    session.flush()
    return ingested, None


def run_seed(
    session: Session,
    *,
    reset: bool,
    heartbeat: Callable[[], None] | None = None,
) -> SeedResult:
    """Point d'entrée unique — `POST /demo/seed`, `apex.cli seed --reset`, `demo_reset` (J3).

    `reset=False` sur un catalogue déjà peuplé est un **no-op** (idempotence : un second
    appel accidentel ne double pas le jeu de démo). `reset=True` truque et régénère
    toujours, à l'identique (graine fixe) — c'est ce qui rend la réinitialisation nocturne
    (Décision N.2) reproductible bit-à-bit.

    `heartbeat` : callback optionnel (`ctx.heartbeat` du job `demo_reset`,
    § worker-queue.instructions.md « les handlers longs appellent `ctx.heartbeat()`
    régulièrement »). No-op par défaut — `apex.cli seed --reset` n'a pas de job à
    rafraîchir, seul le handler de job en fournit un réel.
    """
    heartbeat = heartbeat or (lambda: None)
    started = time.monotonic()
    if not reset:
        if _catalog_is_partial(session):
            raise PartialDemoCatalogError(
                "Catalogue de démo incomplet détecté (« client » peuplé, "
                f"« {LAST_RESET_SETTING_KEY} » absent) — un run précédent n'est jamais allé "
                "à son terme. Relancer avec reset=True pour repartir d'une base propre."
            )
        catalog_exists = session.execute(select(func.count()).select_from(Client)).scalar_one() > 0
        if catalog_exists:
            return SeedResult(reset=False, ran=False)

    if reset:
        _truncate_demo_tables(session)
        session.flush()

    rng = random.Random(SEED)
    faker = Faker("fr_FR")
    faker.seed_instance(SEED)

    storage = get_storage_client()
    thumb_keys = _ensure_sim_thumbnail_pool(storage)

    clients, circuits, drivers, teams, cameras, _owner, photographer = _create_catalog(
        session, rng, faker
    )
    shootings = _create_shootings(session, rng, clients, circuits, photographer)
    engagements_by_shooting = _create_engagements(session, rng, shootings, drivers, teams, clients)

    simulated_count, bucket_counts = _create_simulated_media(
        session,
        rng,
        faker,
        shootings,
        cameras,
        engagements_by_shooting,
        photographer,
        thumb_keys,
    )
    heartbeat()
    real_count, real_skip_reason = _ingest_real_photos(
        session, storage, photographer, shootings, heartbeat=heartbeat
    )

    # Une seule requête pour tout le catalogue (§ Décision N.1) — identique à la
    # réindexation incrémentale, jamais un chemin de projection distinct pour la démo.
    project_media_search(session, None)

    _write_last_reset(session)
    session.flush()

    duration_ms = int((time.monotonic() - started) * 1000)
    return SeedResult(
        reset=reset,
        ran=True,
        clients=len(clients),
        circuits=len(circuits),
        drivers=len(drivers),
        teams=len(teams),
        cameras=len(cameras),
        shootings=len(shootings),
        engagements=sum(len(v) for v in engagements_by_shooting.values()),
        simulated_media=simulated_count,
        real_media=real_count,
        real_photos_skipped_reason=real_skip_reason,
        duration_ms=duration_ms,
        attachment_status_counts=bucket_counts,
    )
