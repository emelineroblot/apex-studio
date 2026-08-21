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
 * Motifs de quarantaine fermés — désormais un **vrai enum du contrat OpenAPI**
 * (`MediaOut.quarantine_reason`), dérivé côté backend du tuple `QUARANTINE_REASONS` de
 * `apex/models/media.py` (verrouillé dans les deux sens par
 * `services/api/tests/test_openapi_contract.py`). Le trou de contrat précédemment signalé
 * ici (mirroir manuel, § `implementation.md` « Garde-fou libellés ») est comblé : ce type
 * est un simple alias vers `schema.d.ts` (généré, `npm run gen:api`), plus une union
 * recopiée à la main — un onzième motif ajouté côté backend et absent d'une régénération
 * fait échouer `Record<QuarantineReason, string>` (`lib/labels.ts`) à la compilation.
 */
export type QuarantineReason = NonNullable<Schemas["MediaOut"]["quarantine_reason"]>;

/**
 * Liste d'exécution des dix motifs, dérivée du type ci-dessus (un type `Literal`/union
 * n'a pas d'existence à l'exécution, `Object.keys` n'y a pas accès directement) via un
 * objet `satisfies Record<QuarantineReason, true>` : toute divergence — motif retiré du
 * contrat ou motif ajouté et non reporté ici — échoue à la compilation (`tsc`/`npm run
 * typecheck`), jamais silencieusement à l'exécution.
 */
const QUARANTINE_REASONS_EXHAUSTIVE = {
  truncated_file: true,
  not_an_image: true,
  unsupported_mime: true,
  dimensions_out_of_range: true,
  aspect_ratio_out_of_range: true,
  exif_inconsistent: true,
  too_large: true,
  quota_exceeded: true,
  ingest_failed: true,
  orphan_object: true,
} satisfies Record<QuarantineReason, true>;
export const QUARANTINE_REASONS = Object.keys(QUARANTINE_REASONS_EXHAUSTIVE) as QuarantineReason[];

/**
 * `AttachmentDetail` — modèle structuré du contrat (`reason` + `candidate_shooting_ids`
 * optionnel, renseigné seulement pour `ambiguous_window`), plus un objet JSON libre.
 * Remplace l'ancien `attachment_detail: dict[str, Any]` côté backend.
 */
export type AttachmentDetail = Schemas["AttachmentDetail"];

/** Motifs du bac « à rattacher » — `AttachmentDetail["reason"]`, vrai enum à 3 valeurs. */
export type UnattachedReason = AttachmentDetail["reason"];

const UNATTACHED_REASONS_EXHAUSTIVE = {
  no_exif_timestamp: true,
  no_matching_window: true,
  ambiguous_window: true,
} satisfies Record<UnattachedReason, true>;
export const UNATTACHED_REASONS = Object.keys(UNATTACHED_REASONS_EXHAUSTIVE) as UnattachedReason[];

/**
 * `QuarantineDetail` — schéma fermé du contrat, 17 clés toutes optionnelles (le détail
 * reste de forme variable selon le motif — `too_large` n'a pas les clés d'`orphan_object`
 * — mais son vocabulaire de clés, lui, est fermé ; `extra="ignore"` côté backend : une
 * 18ᵉ clé de diagnostic ajoutée sans mise à jour du contrat n'est simplement pas exposée,
 * jamais une erreur 500). Remplace l'ancien `quarantine_detail: dict[str, Any]`.
 */
export type QuarantineDetail = Schemas["QuarantineDetail"];
export type QuarantineDetailKey = keyof QuarantineDetail;

// ── J2 — Recherche à facettes (§3-K) ─────────────────────────────────────────────────────
export type FacetTerm = Schemas["FacetTerm"];
export type FacetStatusTerm = Schemas["FacetStatusTerm"];
export type FacetBucket = Schemas["FacetBucket"];
export type Facets = Schemas["Facets"];
export type SearchResponse = Schemas["SearchResponse"];
export type SeriesMode = "collapsed" | "all";
export type SortMode = "shot_at" | "-shot_at";

// ── J2 — File de validation OCR (§3-J) ───────────────────────────────────────────────────
export type ReviewMediaRef = Schemas["ReviewMediaRef"];
export type SuggestedEngagement = Schemas["SuggestedEngagement"];
export type ReviewItem = Schemas["ReviewItem"];
export type ReviewQueueResponse = Schemas["ReviewQueueResponse"];
export type ReviewDecision = Schemas["ReviewDecision"];
export type ReviewDecisionsRequest = Schemas["ReviewDecisionsRequest"];
export type ReviewDecisionError = Schemas["ReviewDecisionError"];
export type ReviewDecisionsResponse = Schemas["ReviewDecisionsResponse"];
/** `ReviewDecision.action` — vrai enum OpenAPI, 3 valeurs. */
export type ReviewAction = ReviewDecision["action"];

export type OcrCandidateOut = Schemas["OcrCandidateOut"];
export type MediaOcrResponse = Schemas["MediaOcrResponse"];
/**
 * `OcrCandidateOut.resolution` — vrai enum OpenAPI (6 valeurs). `Record<OcrResolution,
 * string>` (`lib/labels.ts`) exhaustif au sens du compilateur, même garde-fou que
 * `QuarantineReason` ci-dessus (§ pièges projet — dictionnaires dérivés du contrat).
 */
export type OcrResolution = OcrCandidateOut["resolution"];
const OCR_RESOLUTIONS_EXHAUSTIVE = {
  auto: true,
  review: true,
  abstain: true,
  not_engaged: true,
  accepted: true,
  rejected: true,
} satisfies Record<OcrResolution, true>;
export const OCR_RESOLUTIONS = Object.keys(OCR_RESOLUTIONS_EXHAUSTIVE) as OcrResolution[];

/** `MediaEngagementOut.source` — vrai enum OpenAPI, 2 valeurs. */
export type MediaEngagementSource = MediaEngagementOut["source"];

// ── J2 — Réglages OCR (§3-J.2) ───────────────────────────────────────────────────────────
export type OcrDistribution = Schemas["OcrDistribution"];
export type OcrPreviewDistribution = Schemas["OcrPreviewDistribution"];
export type OcrSettingsOut = Schemas["OcrSettingsOut"];
export type OcrSettingsUpdate = Schemas["OcrSettingsUpdate"];
export type OcrSettingsUpdateResponse = Schemas["OcrSettingsUpdateResponse"];

// ── J2 — Collections ──────────────────────────────────────────────────────────────────────
export type CollectionItemOut = Schemas["CollectionItemOut"];
export type CollectionOut = Schemas["CollectionOut"];
export type CollectionCreate = Schemas["CollectionCreate"];
export type CollectionAddItemsRequest = Schemas["CollectionAddItemsRequest"];
export type CollectionAddItemsResponse = Schemas["CollectionAddItemsResponse"];
/** `CollectionOut.status` — vrai enum OpenAPI, 3 valeurs. */
export type CollectionStatus = CollectionOut["status"];
const COLLECTION_STATUSES_EXHAUSTIVE = {
  draft: true,
  published: true,
  closed: true,
} satisfies Record<CollectionStatus, true>;
export const COLLECTION_STATUSES = Object.keys(COLLECTION_STATUSES_EXHAUSTIVE) as CollectionStatus[];

// ── J2 — Indicateur de rattachement automatique ──────────────────────────────────────────
export type AutoAttachRate = Schemas["AutoAttachRate"];

/**
 * `QuarantineCard.DETAIL_LABELS` est typé `Record<QuarantineDetailKey, string>` : une clé
 * retirée d'ici (donc du contrat) sans être retirée de `DETAIL_LABELS` est une erreur de
 * type ; une clé du contrat absente d'ici (donc absente de `DETAIL_LABELS`) l'est aussi,
 * via le `satisfies` ci-dessous — c'est la classe de régression trouvée trois fois en
 * intégration live J1 (§ `implementation.md`), maintenant fermée par le compilateur dans
 * les deux sens plutôt qu'un seul.
 */
const QUARANTINE_DETAIL_KEYS_EXHAUSTIVE = {
  byte_size: true,
  error: true,
  expected: true,
  format: true,
  found_at: true,
  height: true,
  incoming_bytes: true,
  last_error: true,
  max_upload_bytes: true,
  quota_bytes: true,
  ratio: true,
  reason: true,
  shot_at_exif: true,
  step: true,
  storage_key: true,
  used_bytes: true,
  width: true,
} satisfies Record<QuarantineDetailKey, true>;
export const QUARANTINE_DETAIL_KEYS = Object.keys(QUARANTINE_DETAIL_KEYS_EXHAUSTIVE) as QuarantineDetailKey[];
