"""Sourcing reproductible des ~300 photos réelles du jeu de démonstration (§ brief,
« seul prérequis externe, non bloquant pour le code »).

**Source** : Wikimedia Commons — vérifiée à la main avant ce script (son API répond sans
clé, héberge beaucoup de sport automobile/moto et expose pour chaque fichier sa licence et
son auteur via `prop=imageinfo&iiprop=url|extmetadata`). Alternative envisagée puis écartée :
scraper un site de presse sportive — licences non éditoriales, pas d'API stable, robots.txt
généralement restrictif. Wikimedia Commons est le seul candidat qui donne, pour chaque
fichier, une licence machine-lisible ET l'attribution requise en un seul appel.

**Rejouable, idempotent** : un second run ne retélécharge jamais un fichier déjà accepté ou
déjà rejeté de façon définitive (licence non libre, format inattendu…) — voir
`_load_manifest`/`_save_manifest`. Utile après une interruption réseau en plein milieu des
300 photos, ou pour relancer plus tard avec un `--count` plus élevé.

**Ce que le script vérifie avant d'accepter un fichier** (§ brief, « filtrage qui vérifie
ce qu'il télécharge ») — réutilise **le même code** que le pipeline d'ingestion réel, pas
une réimplémentation parallèle :
- `apex.pipeline.integrity.check_integrity` : fichier non tronqué, format JPEG, dimensions
  et ratio dans la plage acceptée par le pipeline — un fichier que le script accepterait
  mais que le pipeline quarantinerait ensuite serait un déchet déguisé.
- `apex.pipeline.exif.extract_exif` : une date de prise de vue (`DateTimeOriginal`)
  exploitable est **obligatoire** — sans elle, le rattachement temporel ne peut rien
  démontrer. Boîtier/objectif/ISO/vitesse/focale sont journalisés mais pas exigés (« et
  idéalement… », brief) : Commons ne les préserve pas toujours au ré-encodage.
- Licence machine-lisible dans la famille CC0/domaine public/CC BY/CC BY-SA — jamais NC
  (non-commercial) ni ND (pas de dérivés, que la vignette/l'aperçu filigrané violeraient).
- Heuristique best-effort de cadrage : titres/catégories/description évoquant un plan
  rapproché sur des personnes (podium, portrait, interview, tribunes…) sont écartés — la
  discrimination automatique fiable (détection de visages) ajouterait une dépendance non
  autorisée pour ce lot, donc heuristique par mots-clés seulement, documentée comme telle.

**⚠️ Droit à l'image — volontairement distinct du droit d'auteur.** Les licences Creative
Commons ci-dessus couvrent le droit d'auteur du *photographe* sur le cliché. Elles ne
couvrent **jamais** le droit à l'image des personnes visibles (pilotes, public, personnel
de stand), ni les marques/logos présents sur les carrosseries. Ce jeu sert une démonstration
technique interne, pas une publication commerciale ni une exploitation de l'image des
personnes photographiées — voir la note en tête de `docs/demo-photos-attributions.md`
(générée par ce script) et l'étude de cas pour la discussion complète.

Usage :
    uv run python scripts/source_demo_photos.py                  # ~300 photos, reprise
    uv run python scripts/source_demo_photos.py --count 30        # essai rapide
    uv run python scripts/source_demo_photos.py --retry-rejected  # retente les rejets

Toujours exécuté depuis `services/api` (§ AGENTS.md, « Backend, depuis services/api »).
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apex.pipeline.exif import extract_exif
from apex.pipeline.integrity import (
    MAX_ASPECT_RATIO,
    MAX_DIMENSION_PX,
    MIN_ASPECT_RATIO,
    MIN_DIMENSION_PX,
    check_integrity,
)

API_URL = "https://commons.wikimedia.org/w/api.php"
UPLOAD_HOST_TIMEOUT = 30.0

#: Wikimedia exige un User-Agent identifiant (règle d'API etiquette, § brief) — nom
#: d'outil + contact, pas un UA de navigateur générique.
USER_AGENT = (
    "ApexStudioDemoPhotoSourcing/1.0 "
    "(https://github.com/ ; contact: emeline.roblot@emdigital.fr) "
    "python-urllib/apex-demo-seed"
)

#: Catégories Wikimedia Commons couvrant plusieurs disciplines à numéros de course
#: lisibles (§ brief, « élargis : endurance, rallye, karting, superbike, formules de
#: promotion »). Parcourues en round-robin (§ `round_robin`) pour diversifier le jeu
#: plutôt que de vider la première catégorie en premier. Une catégorie absente/vide de
#: Commons est journalisée puis ignorée — jamais fatale (§ `iter_category_candidates`).
#:
#: **Limite constatée à l'usage** (run réel, § `.agent-team/implementation.md`) :
#: `generator=categorymembers&gcmtype=file` ne renvoie que les fichiers rattachés
#: **directement** à la catégorie nommée, jamais ceux de ses sous-catégories (Commons
#: organise souvent par année/événement : « Category:Formula One cars » a peu de fichiers
#: en direct, l'essentiel vit sous « Category:2023 Bahrain Grand Prix », etc.). 18
#: catégories se sont épuisées à 512 candidats considérés pour 201 acceptés — largement
#: sous la cible. `DEFAULT_SEARCH_QUERIES` (recherche plein texte, qui traverse tout
#: l'espace de noms fichier sans se soucier de la profondeur de catégorie) comble l'écart.
DEFAULT_CATEGORIES: tuple[str, ...] = (
    "Formula One cars",
    "Formula 3 cars",
    "Formula 4 cars",
    "Formula Renault",
    "24 Hours of Le Mans",
    "Sports prototypes",
    "World Endurance Championship",
    "World Rally Championship",
    "Rally cars",
    "Rallycross",
    "Karting",
    "Superbike World Championship",
    "MotoGP",
    "Touring car racing",
    "Deutsche Tourenwagen Masters",
    "IndyCar Series",
    "NASCAR",
    "24 Hours of Spa",
)

#: Recherche plein texte (`generator=search`, § docstring de `DEFAULT_CATEGORIES`) — même
#: forme de réponse que `categorymembers` (mêmes champs `imageinfo`/`extmetadata`), donc
#: réutilise exactement `evaluate_candidate`. Termes composés, **entre guillemets**
#: (syntaxe CirrusSearch, moteur de Commons) pour forcer la phrase exacte plutôt qu'un
#: « ET » sur des mots isolés — sans ça, `drag racing car number` a un jour matché un
#: article mentionnant juste « drag » (un bus de ville), sans rapport avec le sport
#: automobile (§ implementation.md, Backend, « faux positif drag/bus »).
DEFAULT_SEARCH_QUERIES: tuple[str, ...] = (
    '"racing car number" livery',
    '"endurance racing" car number',
    '"rally car" number livery',
    '"kart racing" number plate',
    '"superbike racing" number plate',
    '"touring car racing" number',
    '"GT racing" car number livery',
    '"single seater racing car" number',
    '"circuit racing" car livery number',
    '"grand prix car" number',
    '"motorsport race car" pit lane',
    '"hillclimb racing" car number',
    '"drag racing" car number',
    '"autocross racing" car number',
)

#: Best-effort (§ docstring de module) : titres/descriptions/catégories évoquant un plan
#: où le sujet principal est une ou plusieurs personnes plutôt que le véhicule — ou un
#: contenu qui n'est pas une vraie voiture de course du tout (simulateurs/esport, repéré
#: après coup : § implementation.md, « 0005_dtm-esports » — des sportifs sur des cockpits
#: de simulation, aucune carrosserie réelle numérotée, en majorité des personnes).
PEOPLE_HEAVY_KEYWORDS: tuple[str, ...] = (
    "podium",
    "portrait",
    "interview",
    "press conference",
    "pressroom",
    "trophy",
    "grid girl",
    "paddock girl",
    "autograph",
    "fans",
    "crowd",
    "spectator",
    "signing",
    "close-up of",
    "closeup of",
    "headshot",
    "team photo",
    "group photo",
    "celebrat",
    "esports",
    "e-sports",
    "simulator",
    "sim racing",
    "iracing",
    "raceroom",
    "assetto corsa",
    "video game",
    "gaming",
    "trade fair",
    "exhibition stand",
    "car show",
    # Repérés lors de l'audit visuel manuel du run réel (§ implementation.md, Backend) —
    # passent le filtrage automatique (aucun mot-clé « personne ») mais ne montrent ni
    # voiture en action ni numéro lisible : logos, souvenirs, diagrammes pédagogiques,
    # plaques d'immatriculation, stands associatifs posant avec un pilote au premier plan.
    "team logo",
    "engineering logo",
    " logo ",
    "sculpture",
    "license plate",
    "number plate collection",
    "cigarette lighter",
    "die-cast",
    "diecast",
    "memorabilia",
    "collectible",
    "technical institute",
    "freshers fayre",
    "induced drag on traction circle",
)

#: Formats acceptés en amont du téléchargement (le contrôle définitif reste
#: `check_integrity`, exécuté sur les octets réellement reçus).
ALLOWED_MIME = "image/jpeg"

_TAG_RE = re.compile(r"<[^>]+>")
_HREF_RE = re.compile(r'href="([^"]+)"')
_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]+")

DEFAULT_TARGET_COUNT = 300
DEFAULT_MAX_PER_CATEGORY_PAGE = 50
DEFAULT_REQUEST_DELAY = 0.5
#: `0.6` plutôt que `0.3` (valeur initiale) — un run réel a déclenché des `429` côté
#: `upload.wikimedia.org` à `0.25` s (§ docstring `DEFAULT_CATEGORIES`). Ajusté après coup,
#: pas juste retenté : `_http_get` honore aussi `Retry-After` en repli.
DEFAULT_DOWNLOAD_DELAY = 0.6
DEFAULT_MAX_FILE_BYTES = 20_000_000
MANIFEST_FILENAME = ".sourcing-manifest.json"
ATTRIBUTIONS_DOC_RELATIVE = Path("docs") / "demo-photos-attributions.md"


# --------------------------------------------------------------------------------------
# Utilitaires purs (couverts par tests/tooling/test_source_demo_photos_filters.py — aucun
# appel réseau dans ces fonctions, testables hors ligne).
# --------------------------------------------------------------------------------------


def strip_html(value: str) -> str:
    """`extmetadata.Artist`/`.Credit` sont du HTML minimal (`<a>`, `<span>`) — texte brut."""
    return html.unescape(_TAG_RE.sub("", value)).strip()


def first_href(value: str) -> str | None:
    match = _HREF_RE.search(value)
    if not match:
        return None
    href = match.group(1)
    return f"https:{href}" if href.startswith("//") else href


def slugify(title: str) -> str:
    base = title.removeprefix("File:")
    base = re.sub(r"\.[A-Za-z0-9]+$", "", base)  # extension d'origine
    base = _NON_ALNUM_RE.sub("-", base).strip("-").lower()
    return (base[:60] or "photo").strip("-") or "photo"


def local_filename(index: int, title: str) -> str:
    return f"{index:04d}_{slugify(title)}.jpg"


def license_is_free_enough(machine_code: str | None) -> bool:
    """CC0/domaine public/CC BY/CC BY-SA — jamais NC (non-commercial) ni ND (pas de
    dérivés, que la vignette et l'aperçu filigrané violeraient — § Décision H.3 du plan).
    """
    if not machine_code:
        return False
    code = machine_code.strip().lower()
    if code.startswith("cc0") or code.startswith("pd") or "public domain" in code:
        return True
    if code.startswith("cc-by"):
        return "nc" not in code and "nd" not in code
    return False


def is_people_heavy(*text_fields: str | None) -> bool:
    """Heuristique best-effort par mots-clés (§ docstring de module) — pas de détection
    de visages : aucune dépendance supplémentaire n'est autorisée pour ce lot.
    """
    haystack = " ".join(f for f in text_fields if f).lower()
    return any(keyword in haystack for keyword in PEOPLE_HEAVY_KEYWORDS)


def dimensions_plausible(width: int, height: int) -> bool:
    """Pré-filtre côté métadonnées API — les **mêmes** seuils que
    `apex.pipeline.integrity.check_integrity`, pour ne jamais télécharger un fichier que
    le pipeline rejetterait de toute façon. Le contrôle définitif reste `check_integrity`
    sur les octets réellement reçus (les dimensions annoncées par l'API peuvent être
    inexactes dans de rares cas).
    """
    if width < MIN_DIMENSION_PX or height < MIN_DIMENSION_PX:
        return False
    if width > MAX_DIMENSION_PX or height > MAX_DIMENSION_PX:
        return False
    ratio = width / height if height else 0.0
    return MIN_ASPECT_RATIO <= ratio <= MAX_ASPECT_RATIO


# --------------------------------------------------------------------------------------
# Accès réseau — Wikimedia Commons
# --------------------------------------------------------------------------------------


def _http_get(url: str, *, timeout: float, attempts: int = 4) -> bytes:
    """`attempts=4` par défaut : `429` (constaté en run réel, § `DEFAULT_CATEGORIES`) mérite
    un repli plus généreux qu'une simple panne réseau — on n'abandonne pas un candidat déjà
    accepté au filtrage métadonnées pour une limite de débit temporaire, on ralentit et on
    réessaie. Honore `Retry-After` quand Wikimedia le fournit, sinon repli progressif.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return response.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if attempt < attempts:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                delay = (
                    float(retry_after) if retry_after and retry_after.isdigit() else 8.0 * attempt
                )
                time.sleep(delay)
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(1.5 * attempt)  # repli progressif — service public gratuit
    assert last_error is not None
    raise last_error


def _api_query(params: dict[str, str], *, timeout: float) -> dict[str, Any]:
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    body = _http_get(url, timeout=timeout)
    result: dict[str, Any] = json.loads(body)
    return result


def iter_category_candidates(
    category: str,
    *,
    request_delay: float,
    timeout: float,
    page_limit: int = DEFAULT_MAX_PER_CATEGORY_PAGE,
):
    """Pages d'une catégorie Commons, une image à la fois, avec pagination `gcmcontinue`.

    Ne lève jamais pour une catégorie inexistante/vide côté Commons — journalise et
    s'arrête, le reste du run continue avec les autres catégories (§ docstring module).
    """
    params: dict[str, str] = {
        "action": "query",
        "format": "json",
        "generator": "categorymembers",
        "gcmtitle": f"Category:{category}",
        "gcmtype": "file",
        "gcmlimit": str(page_limit),
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|size|mime",
    }
    while True:
        try:
            data = _api_query(params, timeout=timeout)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"  [{category}] requête échouée, catégorie abandonnée : {exc}")
            return

        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            yield category, page

        cont = data.get("continue")
        if not cont:
            return
        params.update(cont)
        time.sleep(request_delay)


def iter_search_candidates(
    query: str,
    *,
    request_delay: float,
    timeout: float,
    page_limit: int = DEFAULT_MAX_PER_CATEGORY_PAGE,
    max_pages: int = 20,
):
    """Recherche plein texte (`generator=search`, namespace fichier) — même forme de
    réponse que `iter_category_candidates` (§ docstring `DEFAULT_SEARCH_QUERIES`), donc
    les candidats produits sont évalués par la même `evaluate_candidate`.

    `max_pages` borne la pagination (contrairement aux catégories, une recherche plein
    texte generique peut renvoyer des dizaines de milliers de résultats — pas question de
    tout parcourir pour viser ~300 photos au total).
    """
    params: dict[str, str] = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrnamespace": "6",
        "gsrsearch": query,
        "gsrlimit": str(page_limit),
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|size|mime",
    }
    label = f"recherche : {query}"
    for _ in range(max_pages):
        try:
            data = _api_query(params, timeout=timeout)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"  [{label}] requête échouée, recherche abandonnée : {exc}")
            return

        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            yield label, page

        cont = data.get("continue")
        if not cont:
            return
        params.update(cont)
        time.sleep(request_delay)


def round_robin(iterators: list[Any]):
    """Alterne entre les générateurs de catégories — diversifie les disciplines plutôt
    que d'épuiser la première catégorie avant de passer à la suivante.
    """
    active = list(iterators)
    while active:
        still_active = []
        for it in active:
            try:
                yield next(it)
                still_active.append(it)
            except StopIteration:
                continue
        active = still_active


# --------------------------------------------------------------------------------------
# Manifeste de reprise (dans le dossier de sortie, gitignoré comme le reste)
# --------------------------------------------------------------------------------------


@dataclass(slots=True)
class Manifest:
    path: Path
    entries: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> Manifest:
        if not path.is_file():
            return cls(path=path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls(path=path)
        return cls(path=path, entries=data.get("entries", {}))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "generated_at": datetime.now(UTC).isoformat(),
            "entries": self.entries,
        }
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def accepted_count_on_disk(self, out_dir: Path) -> int:
        return sum(
            1
            for entry in self.entries.values()
            if entry.get("status") == "accepted" and (out_dir / entry["filename"]).is_file()
        )


# --------------------------------------------------------------------------------------
# Cœur du sourcing
# --------------------------------------------------------------------------------------


@dataclass(slots=True)
class RunStats:
    considered: int = 0
    accepted: int = 0
    rejected_by_reason: dict[str, int] = field(default_factory=dict)

    def reject(self, reason: str) -> None:
        self.rejected_by_reason[reason] = self.rejected_by_reason.get(reason, 0) + 1

    @property
    def rejected(self) -> int:
        return sum(self.rejected_by_reason.values())


def _extmetadata_value(extmetadata: dict[str, Any], key: str) -> str | None:
    entry = extmetadata.get(key)
    if not isinstance(entry, dict):
        return None
    value = entry.get("value")
    return str(value) if value is not None else None


def evaluate_candidate(
    category: str, page: dict[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    """Filtrage sur les seules métadonnées API (avant tout téléchargement).

    Renvoie `(info, None)` si le candidat mérite d'être téléchargé, ou `(None, reason)`
    s'il est rejeté sans avoir consommé de bande passante.
    """
    imageinfo_list = page.get("imageinfo") or []
    if not imageinfo_list:
        return None, "no_imageinfo"
    info = imageinfo_list[0]

    if info.get("mime") != ALLOWED_MIME:
        return None, f"unsupported_mime:{info.get('mime')}"

    width, height = info.get("width"), info.get("height")
    if not isinstance(width, int) or not isinstance(height, int):
        return None, "missing_dimensions"
    if not dimensions_plausible(width, height):
        return None, "dimensions_out_of_range"

    size = info.get("size")
    if isinstance(size, int) and size > DEFAULT_MAX_FILE_BYTES:
        return None, "file_too_large"

    extmetadata = info.get("extmetadata") or {}
    license_code = _extmetadata_value(extmetadata, "License")
    if not license_is_free_enough(license_code):
        return None, f"license_not_free:{license_code}"

    title = page.get("title", "")
    description = _extmetadata_value(extmetadata, "ImageDescription") or ""
    object_name = _extmetadata_value(extmetadata, "ObjectName") or ""
    categories = _extmetadata_value(extmetadata, "Categories") or ""
    if is_people_heavy(title, description, object_name, categories):
        return None, "people_heavy_framing"

    return {
        "category": category,
        "title": title,
        "url": info.get("url"),
        "descriptionurl": info.get("descriptionurl"),
        "width": width,
        "height": height,
        "license_code": license_code,
        "license_short": _extmetadata_value(extmetadata, "LicenseShortName") or license_code,
        "license_url": _extmetadata_value(extmetadata, "LicenseUrl"),
        "artist_html": _extmetadata_value(extmetadata, "Artist"),
        "credit_html": _extmetadata_value(extmetadata, "Credit"),
    }, None


def process_candidate(
    info: dict[str, Any],
    *,
    index: int,
    out_dir: Path,
    timeout: float,
) -> tuple[dict[str, Any] | None, str | None]:
    """Télécharge et valide un candidat déjà retenu au filtrage métadonnées.

    Renvoie `(manifest_entry, None)` si accepté (fichier déjà écrit sur disque), ou
    `(None, reason)` si rejeté après téléchargement (intégrité ou absence d'EXIF).
    """
    url = info["url"]
    if not url:
        return None, "missing_url"
    try:
        data = _http_get(url, timeout=timeout)
    except (urllib.error.URLError, TimeoutError) as exc:
        return None, f"download_failed:{exc}"

    integrity = check_integrity(data)
    if not integrity.ok:
        return None, f"integrity:{integrity.reason}"

    exif = extract_exif(data)
    if exif.shot_at_exif is None:
        return None, "missing_exif_date"

    filename = local_filename(index, info["title"])
    (out_dir / filename).write_bytes(data)

    author = strip_html(info["artist_html"]) if info.get("artist_html") else None
    author_url = first_href(info["artist_html"]) if info.get("artist_html") else None
    credit = strip_html(info["credit_html"]) if info.get("credit_html") else None

    entry = {
        "status": "accepted",
        "filename": filename,
        "category": info["category"],
        "title": info["title"],
        "source_url": info["descriptionurl"],
        "license_code": info["license_code"],
        "license_short": info["license_short"],
        "license_url": info["license_url"],
        "author": author,
        "author_url": author_url,
        "credit": credit,
        "width": integrity.width,
        "height": integrity.height,
        "exif": {
            "shot_at": exif.shot_at_exif.isoformat() if exif.shot_at_exif else None,
            "camera_make": exif.camera_make,
            "camera_model": exif.camera_model,
            "lens_model": exif.lens_model,
            "iso": exif.iso,
            "shutter_speed_label": exif.shutter_speed_label,
            "aperture": exif.aperture,
            "focal_length": exif.focal_length,
            "gps": exif.gps_lat is not None and exif.gps_lon is not None,
        },
    }
    return entry, None


def run_sourcing(
    *,
    out_dir: Path,
    target_count: int,
    categories: tuple[str, ...],
    search_queries: tuple[str, ...],
    request_delay: float,
    download_delay: float,
    timeout: float,
    retry_rejected: bool,
) -> RunStats:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = Manifest.load(out_dir / MANIFEST_FILENAME)
    stats = RunStats()

    already_accepted = manifest.accepted_count_on_disk(out_dir)
    next_index = 1 + max(
        (
            int(Path(e["filename"]).stem.split("_", 1)[0])
            for e in manifest.entries.values()
            if e.get("status") == "accepted" and "filename" in e
        ),
        default=0,
    )
    print(f"Déjà acceptées sur disque : {already_accepted}/{target_count} (reprise).")
    if already_accepted >= target_count:
        print("Cible déjà atteinte — rien à télécharger (utiliser --count pour l'augmenter).")
        return stats

    seen_pageids = set(manifest.entries.keys())
    if retry_rejected:
        seen_pageids = {pid for pid, e in manifest.entries.items() if e.get("status") != "rejected"}

    generators = [
        iter_category_candidates(cat, request_delay=request_delay, timeout=timeout)
        for cat in categories
    ] + [
        iter_search_candidates(query, request_delay=request_delay, timeout=timeout)
        for query in search_queries
    ]

    accepted_this_run = 0
    for category, page in round_robin(generators):
        if already_accepted + accepted_this_run >= target_count:
            break
        pageid = str(page.get("pageid"))
        if pageid in seen_pageids:
            continue
        seen_pageids.add(pageid)
        stats.considered += 1

        info, reject_reason = evaluate_candidate(category, page)
        if info is None:
            assert reject_reason is not None
            stats.reject(reject_reason)
            manifest.entries[pageid] = {
                "status": "rejected",
                "reason": reject_reason,
                "title": page.get("title"),
                "category": category,
            }
            manifest.save()
            continue

        entry, download_reject_reason = process_candidate(
            info, index=next_index, out_dir=out_dir, timeout=timeout
        )
        if entry is None:
            assert download_reject_reason is not None
            stats.reject(download_reject_reason)
            manifest.entries[pageid] = {
                "status": "rejected",
                "reason": download_reject_reason,
                "title": page.get("title"),
                "category": category,
            }
            manifest.save()
            time.sleep(download_delay)
            continue

        manifest.entries[pageid] = entry
        manifest.save()
        stats.accepted += 1
        accepted_this_run += 1
        next_index += 1
        print(f"  [{accepted_this_run + already_accepted:04d}/{target_count}] {entry['filename']}")
        time.sleep(download_delay)

    return stats


# --------------------------------------------------------------------------------------
# Fichier d'attributions versionné
# --------------------------------------------------------------------------------------


def write_attributions_doc(manifest: Manifest, *, doc_path: Path, out_dir: Path) -> int:
    accepted = [(pid, e) for pid, e in manifest.entries.items() if e.get("status") == "accepted"]
    accepted.sort(key=lambda item: item[1]["filename"])

    lines: list[str] = [
        "# Attributions — jeu de démonstration de photos réelles (Wikimedia Commons)",
        "",
        "> Généré automatiquement par `services/api/scripts/source_demo_photos.py` — "
        "ne pas éditer à la main, relancer le script pour le régénérer.",
        f"> Dernière génération : {datetime.now(UTC).isoformat()} — {len(accepted)} photos.",
        "",
        "## Droit à l'image — distinct du droit d'auteur",
        "",
        "Les licences ci-dessous (Creative Commons, domaine public) couvrent **uniquement "
        "le droit d'auteur du photographe** sur le cliché. Elles ne couvrent **pas** le "
        "droit à l'image des personnes visibles (pilotes, public, personnel de stand), ni "
        "les marques/logos présents sur les carrosseries et les combinaisons. Ce jeu de "
        "photos est utilisé à des fins de démonstration technique interne (portfolio), "
        "jamais publié en dehors de ce cadre ni exploité commercialement — l'attribution "
        "ci-dessous satisfait l'exigence des licences CC BY / CC BY-SA, elle ne règle pas "
        "la question du droit à l'image, qui reste hors du périmètre que ces licences "
        "peuvent couvrir.",
        "",
        "## Attribution",
        "",
        "| Fichier | Titre Wikimedia Commons | Auteur | Licence | Source |",
        "|---|---|---|---|---|",
    ]
    for _pid, entry in accepted:
        author = entry.get("author") or "auteur non renseigné"
        license_short = entry.get("license_short") or entry.get("license_code") or "?"
        source = entry.get("source_url") or ""
        title = entry.get("title") or ""
        filename = entry["filename"]
        lines.append(f"| `{filename}` | {title} | {author} | {license_short} | {source} |")

    lines += [
        "",
        "## Répartition par licence",
        "",
    ]
    by_license: dict[str, int] = {}
    for _pid, entry in accepted:
        key = entry.get("license_short") or entry.get("license_code") or "?"
        by_license[key] = by_license.get(key, 0) + 1
    for key, count in sorted(by_license.items(), key=lambda kv: -kv[1]):
        lines.append(f"- {key} : {count}")

    lines += [
        "",
        "## Répartition par catégorie source",
        "",
    ]
    by_category: dict[str, int] = {}
    for _pid, entry in accepted:
        key = entry.get("category") or "?"
        by_category[key] = by_category.get(key, 0) + 1
    for key, count in sorted(by_category.items(), key=lambda kv: -kv[1]):
        lines.append(f"- {key} : {count}")

    with_exif_camera = sum(1 for _pid, e in accepted if (e.get("exif") or {}).get("camera_model"))
    lines += [
        "",
        "## Complétude EXIF",
        "",
        f"- Date de prise de vue exploitable : {len(accepted)}/{len(accepted)} "
        "(condition d'acceptation — § script)",
        f"- Boîtier/objectif renseignés en plus de la date : {with_exif_camera}/{len(accepted)}",
        "",
        f"Photos stockées localement dans `{out_dir}` (dossier gitignoré, jamais versionné).",
        "",
    ]

    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(accepted)


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def _default_out_dir() -> Path:
    # `services/api/demo-photos` — le chemin réellement lu par `settings.real_photos_dir`
    # (`./demo-photos`) quand les commandes tournent « depuis services/api »
    # (AGENTS.md, § Commandes). Résolu depuis l'emplacement du script, pas le CWD courant,
    # pour rester correct quel que soit le répertoire d'où on l'invoque.
    return Path(__file__).resolve().parent.parent / "demo-photos"


def _default_doc_path() -> Path:
    # `docs/demo-photos-attributions.md` à la racine du dépôt (`services/api/scripts/` ->
    # remonter de deux niveaux).
    return Path(__file__).resolve().parent.parent.parent.parent / ATTRIBUTIONS_DOC_RELATIVE


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=DEFAULT_TARGET_COUNT)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--doc-path", type=Path, default=None)
    parser.add_argument(
        "--categories",
        type=str,
        default=None,
        help="Liste séparée par des virgules, remplace la liste par défaut.",
    )
    parser.add_argument(
        "--search-queries",
        type=str,
        default=None,
        help=(
            "Liste séparée par des virgules (recherche plein texte, § DEFAULT_SEARCH_QUERIES), "
            "remplace la liste par défaut. Passer une chaîne vide pour la désactiver."
        ),
    )
    parser.add_argument("--request-delay", type=float, default=DEFAULT_REQUEST_DELAY)
    parser.add_argument("--download-delay", type=float, default=DEFAULT_DOWNLOAD_DELAY)
    parser.add_argument("--timeout", type=float, default=UPLOAD_HOST_TIMEOUT)
    parser.add_argument(
        "--retry-rejected",
        action="store_true",
        help="Retente les candidats déjà rejetés lors d'un run précédent.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_dir = args.out_dir or _default_out_dir()
    doc_path = args.doc_path or _default_doc_path()
    categories = (
        tuple(c.strip() for c in args.categories.split(",") if c.strip())
        if args.categories
        else DEFAULT_CATEGORIES
    )
    search_queries = (
        tuple(q.strip() for q in args.search_queries.split(",") if q.strip())
        if args.search_queries is not None
        else DEFAULT_SEARCH_QUERIES
    )

    print(f"Sortie : {out_dir}")
    print(f"Catégories ({len(categories)}) : {', '.join(categories)}")
    print(f"Recherches ({len(search_queries)}) : {', '.join(search_queries)}")

    stats = run_sourcing(
        out_dir=out_dir,
        target_count=args.count,
        categories=categories,
        search_queries=search_queries,
        request_delay=args.request_delay,
        download_delay=args.download_delay,
        timeout=args.timeout,
        retry_rejected=args.retry_rejected,
    )

    manifest = Manifest.load(out_dir / MANIFEST_FILENAME)
    total_accepted = write_attributions_doc(manifest, doc_path=doc_path, out_dir=out_dir)

    print()
    print(f"Candidats considérés ce run : {stats.considered}")
    print(f"Acceptés ce run             : {stats.accepted}")
    print(f"Rejetés ce run               : {stats.rejected}")
    if stats.considered:
        rate = stats.rejected / stats.considered * 100
        print(f"Taux de rejet ce run          : {rate:.1f} %")
    if stats.rejected_by_reason:
        print("Détail des rejets :")
        for reason, count in sorted(stats.rejected_by_reason.items(), key=lambda kv: -kv[1]):
            print(f"  - {reason} : {count}")
    print(f"Total accepté sur disque      : {total_accepted}")
    print(f"Fichier d'attributions        : {doc_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
