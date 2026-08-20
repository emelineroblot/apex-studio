/**
 * Alias de confort vers les schémas générés (`schema.d.ts`, GÉNÉRÉ — ne pas éditer).
 * Un seul endroit à modifier si l'OpenAPI change de nommage.
 */
import type { components } from "./schema.d.ts";

type Schemas = components["schemas"];

export type Role = Schemas["UserOut"]["role"];
export type UserOut = Schemas["UserOut"];
/** `GET /users` (rôle `owner` uniquement) — sans `email`, contrairement à `UserOut`. */
export type UserSummary = Schemas["UserSummary"];
export type DemoAccount = Schemas["DemoAccount"];
export type TokenResponse = Schemas["TokenResponse"];

export type ClientOut = Schemas["ClientOut"];
export type ClientCreate = Schemas["ClientCreate"];
export type ClientUpdate = Schemas["ClientUpdate"];
export type ClientKind = ClientOut["kind"];

export type CircuitOut = Schemas["CircuitOut"];
export type CircuitCreate = Schemas["CircuitCreate"];

export type DriverOut = Schemas["DriverOut"];
export type DriverCreate = Schemas["DriverCreate"];

export type TeamOut = Schemas["TeamOut"];
export type TeamCreate = Schemas["TeamCreate"];

export type ShootingOut = Schemas["ShootingOut"];
export type ShootingCreate = Schemas["ShootingCreate"];
export type ShootingPatch = Schemas["ShootingPatch"];
export type ShootingSummary = Schemas["ShootingSummary"];
export type ShootingStatus = ShootingOut["status"];
export type StaffMember = Schemas["StaffMember"];

export type EngagementOut = Schemas["EngagementOut"];
export type EngagementCreate = Schemas["EngagementCreate"];
export type EngagementPatch = Schemas["EngagementPatch"];
export type EngagementImportResult = Schemas["EngagementImportResult"];
export type EngagementImportError = Schemas["EngagementImportError"];

export type BatchCreateResponse = Schemas["BatchCreateResponse"];
export type FileUploadResponse = Schemas["FileUploadResponse"];
export type BatchStatusResponse = Schemas["BatchStatusResponse"];
export type BatchStatusCounts = Schemas["BatchStatusCounts"];
export type BatchCloseResponse = Schemas["BatchCloseResponse"];

export type MediaSummary = Schemas["MediaSummary"];
export type MediaOut = Schemas["MediaOut"];
export type MediaExif = Schemas["MediaExif"];
export type MediaEngagementOut = Schemas["MediaEngagementOut"];
export type IngestStatus = MediaSummary["ingest_status"];
export type AttachmentStatus = MediaSummary["attachment_status"];
export type MediaVariant = "thumb" | "preview" | "hd";
export type PipelineEventOut = Schemas["PipelineEventOut"];

export type CameraOut = Schemas["CameraOut"];
export type CameraPatch = Schemas["CameraPatch"];
/**
 * `reattached` est désormais exposé nativement par `openapi.json` (voir description du
 * schéma généré dans `schema.d.ts`) — le patch temporaire posé en revue J1 (constat 🟠
 * `cameras/page.tsx`) est retiré, cet alias redevient un simple passe-plat.
 */
export type CameraPatchResponse = Schemas["CameraPatchResponse"];

export type Page<T> = { items: T[]; next_cursor: string | null; total: number | null };

/**
 * Motifs de quarantaine fermés (§ modèle `media.py`, `QUARANTINE_REASONS`).
 *
 * ⚠️ **Mirroir manuel, pas dérivé de `schema.d.ts`** : le backend garde ce tuple fermé
 * uniquement en Python (contrainte CHECK SQL + tuple `QUARANTINE_REASONS`) — le schéma
 * Pydantic `MediaOut.quarantine_reason`/`MediaSummary` l'expose en `str | null` **sans**
 * `Literal[...]`, donc `openapi.json` ne porte aucun `enum` pour ce champ et
 * `openapi-typescript` ne peut pas nous générer ce type. Trou de contrat signalé côté
 * backend (§ `implementation.md`, « Garde-fou libellés ») — non contournable ici sans
 * modifier `services/api/src/apex/schemas/media.py` (backend figé sur cette branche).
 * Tant que ce n'est pas corrigé côté backend, ce tuple doit être tenu à jour à la main en
 * même temps que `apex/models/media.py::QUARANTINE_REASONS`.
 */
export const QUARANTINE_REASONS = [
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
] as const;
export type QuarantineReason = (typeof QUARANTINE_REASONS)[number];

/**
 * Motifs du bac « à rattacher » — `attachment_detail.reason` (§ `pipeline/attach_time.py`).
 *
 * Même trou de contrat que `QUARANTINE_REASONS` ci-dessus, en pire : `attachment_detail`
 * est typé `{ [key: string]: unknown } | null` dans `openapi.json` (JSON totalement
 * libre, pas même un `string` simple pour `reason`) — aucun enum à générer. Mirroir manuel
 * du tuple fermé réellement écrit par `attach_media_by_time`.
 */
export const UNATTACHED_REASONS = ["no_exif_timestamp", "no_matching_window", "ambiguous_window"] as const;
export type UnattachedReason = (typeof UNATTACHED_REASONS)[number];

/**
 * Clés effectivement écrites par le backend dans `Media.quarantine_detail`, relevées à la
 * source sur cette branche (`quarantine_detail` est `{ [key: string]: unknown } | null`
 * dans le contrat OpenAPI — JSON libre, aucun enum possible à générer, même trou que
 * ci-dessus) :
 * - `pipeline/integrity.py::check_integrity` → `byte_size`, `format`, `width`, `height`,
 *   `expected`, `ratio`, `error`
 * - `routers/batches.py::upload_file` (413 `too_large`/`quota_exceeded`) → `byte_size`,
 *   `max_upload_bytes`, `used_bytes`, `incoming_bytes`, `quota_bytes`
 * - `pipeline/ingest.py` (motif `exif_inconsistent`) → `shot_at_exif`
 * - `pipeline/ingest.py` (motif `ingest_failed`, échec d'étape rattrapé) → `step`, `error`
 * - `queue/handlers/ingest_media.py::_on_dead` (motif `ingest_failed`, job mort) →
 *   `reason`, `last_error`
 * - `queue/handlers/sweep_orphans.py` (motif `orphan_object`) → `storage_key`, `found_at`
 *
 * `QuarantineCard.DETAIL_LABELS` est typé `Record<QuarantineDetailKey, string>` : une clé
 * listée ici sans libellé français est désormais une **erreur de type**, pas un code
 * technique brut affiché à l'écran (c'est la classe de régression trouvée trois fois en
 * intégration live J1, § `implementation.md`). Si le backend écrit une clé absente d'ici,
 * en revanche, rien ne le détecte à la compilation — seul un test source (§
 * `QuarantineCard.detail-labels.test.ts`) ou une revue peut l'attraper.
 */
export const QUARANTINE_DETAIL_KEYS = [
  "byte_size",
  "format",
  "width",
  "height",
  "expected",
  "ratio",
  "error",
  "max_upload_bytes",
  "used_bytes",
  "incoming_bytes",
  "quota_bytes",
  "shot_at_exif",
  "step",
  "reason",
  "last_error",
  "storage_key",
  "found_at",
] as const;
export type QuarantineDetailKey = (typeof QUARANTINE_DETAIL_KEYS)[number];
