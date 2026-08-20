"""Schémas `media` — deux axes d'état orthogonaux (§3-F.2) : ne jamais les fusionner.

`QuarantineReason` et `AttachmentUnattachedReason` sont des unions closes (`Literal`), pas de
simples `str` : c'est ce qui rend un motif ajouté côté backend sans mise à jour du dictionnaire
de libellés frontend une **erreur de compilation** côté TypeScript généré, plutôt qu'un code
technique affiché tel quel à l'écran (régression J1 constatée trois fois). Les valeurs sont
dérivées de `apex.models.media.QUARANTINE_REASONS` / `UNATTACHED_REASONS` — seules sources de
vérité — et leur correspondance exacte est verrouillée par
`tests/test_openapi_contract.py::test_quarantine_reason_enum_matches_model`.

`quarantine_detail` a une forme qui varie réellement selon le motif (`too_large` n'a pas les
mêmes clés que `orphan_object`) — mentir en imposant un schéma unique où toutes les clés
seraient requises serait un faux contrat. Mais le **vocabulaire de clés** que ces formes
puisent est, lui, fermé (`apex.models.media.QUARANTINE_DETAIL_KEYS`) : modélisé ici comme un
objet à propriétés **optionnelles** (`QuarantineDetail`), pas comme un dict libre — le
compromis honnête entre un faux enum et un contrat qui n'apprend rien au frontend.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

IngestStatus = Literal["uploaded", "processing", "ingested", "quarantined"]
AttachmentStatus = Literal[
    "unattached", "shooting_attached", "engagement_attached", "pending_review", "inconsistent"
]
AttachmentSource = Literal["pipeline_time", "pipeline_ocr", "human"]
MediaVariant = Literal["thumb", "preview", "hd"]

# Doit rester égal, valeur pour valeur, à `apex.models.media.QUARANTINE_REASONS` (CHECK en
# base). Voir docstring de module.
QuarantineReason = Literal[
    "truncated_file",
    "not_an_image",
    "unsupported_mime",
    "dimensions_out_of_range",
    "aspect_ratio_out_of_range",
    "exif_inconsistent",
    "too_large",
    "quota_exceeded",
    "ingest_failed",
    "orphan_object",
]

# Doit rester égal, valeur pour valeur, à `apex.models.media.UNATTACHED_REASONS`. Voir
# docstring de module.
AttachmentUnattachedReason = Literal[
    "no_exif_timestamp",
    "no_matching_window",
    "ambiguous_window",
]


class AttachmentDetail(BaseModel):
    """Motif de non-rattachement (`attachment_detail` quand `attachment_status='unattached'`),
    écrit par `apex/pipeline/attach_time.py`. `candidate_shooting_ids` n'est renseigné que
    pour `ambiguous_window` — les autres motifs n'ont pas de détail additionnel.
    """

    reason: AttachmentUnattachedReason
    candidate_shooting_ids: list[int] | None = None


class QuarantineDetail(BaseModel):
    """Détail d'une quarantaine (`quarantine_detail`) — clés closes
    (`apex.models.media.QUARANTINE_DETAIL_KEYS`), toutes optionnelles puisque chaque motif de
    quarantaine n'en écrit qu'un sous-ensemble. `model_config.extra="ignore"` : un champ de
    diagnostic ajouté côté backend sans mise à jour immédiate de ce schéma ne doit jamais faire
    échouer la sérialisation de la fiche média (fail-soft) — c'est le test de cohérence
    (`tests/test_openapi_contract.py`) qui détecte l'oubli, pas une 500 en production.
    """

    model_config = ConfigDict(extra="ignore")

    byte_size: int | None = None
    error: str | None = None
    expected: str | None = None
    format: str | None = None
    found_at: str | None = None
    height: int | None = None
    incoming_bytes: int | None = None
    last_error: str | None = None
    max_upload_bytes: int | None = None
    quota_bytes: int | None = None
    ratio: float | None = None
    reason: str | None = None
    shot_at_exif: str | None = None
    step: str | None = None
    storage_key: str | None = None
    used_bytes: int | None = None
    width: int | None = None


class MediaSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thumb_url: str
    shot_at: datetime | None
    ingest_status: IngestStatus
    attachment_status: AttachmentStatus
    shooting_id: int | None
    is_simulated: bool
    duplicate_of_media_id: int | None
    # Manque de contrat relevé en intégration live J1 : sans ces deux champs, la grille ne
    # peut ni savoir qu'un média appartient à une rafale, ni afficher le compte de la série
    # (« une vignette + N clichés ») sans une requête par média. `series_id` seul suffirait
    # à filtrer côté serveur (voir `GET /media?series=`) mais pas à afficher le badge côté
    # client — d'où `series_member_count`, lu depuis `media_series.member_count` (déjà
    # tenu à jour par `pipeline/series.py`), jamais recalculé ici.
    series_id: int | None
    series_member_count: int | None


class MediaEngagementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    engagement_id: int
    car_number: str
    source: Literal["ocr", "human"]
    confidence: float | None


class MediaExif(BaseModel):
    camera_id: int | None
    lens_model: str | None
    iso: int | None
    shutter_speed_sec: float | None
    shutter_speed_label: str | None
    aperture: float | None
    focal_length: float | None
    gps_lat: float | None
    gps_lon: float | None
    exif_raw: dict[str, Any] | None


class MediaOut(BaseModel):
    """Fiche média complète : EXIF, série, doublon, engagements, journal d'événements."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    original_filename: str
    byte_size: int
    mime: str | None
    width: int | None
    height: int | None
    shot_at_exif: datetime | None
    shot_at: datetime | None
    exif: MediaExif
    phash: int | None
    sharpness: float | None
    series_id: int | None
    is_series_representative: bool
    duplicate_of_media_id: int | None
    ingest_status: IngestStatus
    quarantine_reason: QuarantineReason | None
    quarantine_detail: QuarantineDetail | None
    attachment_status: AttachmentStatus
    attachment_source: AttachmentSource | None
    attachment_detail: AttachmentDetail | None
    shooting_id: int | None
    is_simulated: bool
    caption: str | None
    keywords: list[str] | None
    engagements: list[MediaEngagementOut]
    events: list[str]


class MediaAttachRequest(BaseModel):
    shooting_id: int


class MediaEngagementAttachRequest(BaseModel):
    """Corps de `POST /media/{id}/engagements` (J2, rattachement manuel `source='human'`)."""

    engagement_id: int
