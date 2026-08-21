/**
 * Dictionnaires de libellés français — un motif technique n'est **jamais** affiché tel
 * quel à l'écran (invariant `AGENTS.md` : bac explicite, motif lisible).
 */
import type {
  AttachmentStatus,
  ClientKind,
  CollectionStatus,
  IngestStatus,
  MediaEngagementSource,
  OcrResolution,
  QuarantineReason,
  Role,
  ShootingStatus,
  UnattachedReason,
} from "@/lib/api/types";

export const ROLE_LABELS: Record<Role, string> = {
  owner: "Dirigeant·e",
  photographer: "Photographe",
};

export const INGEST_STATUS_LABELS: Record<IngestStatus, string> = {
  uploaded: "Déposé",
  processing: "En traitement",
  ingested: "Ingéré",
  quarantined: "En quarantaine",
};

export const ATTACHMENT_STATUS_LABELS: Record<AttachmentStatus, string> = {
  unattached: "À rattacher",
  shooting_attached: "Rattaché au shooting",
  engagement_attached: "Rattaché à un engagement",
  pending_review: "En file de validation",
  inconsistent: "Incohérent",
};

/**
 * §3-F.2 du plan, énumération fermée `QUARANTINE_REASONS` de `apex/models/media.py`,
 * désormais un vrai enum OpenAPI (`QuarantineReason` dérivé de `schema.d.ts`, § `lib/api/
 * types.ts`) : ce `Record` est exhaustif au sens du compilateur, pas seulement au sens du
 * commentaire. Le repli via `quarantineReasonLabel` reste utile en défense pour une
 * valeur qui apparaîtrait à l'exécution sans être encore reflétée par une régénération du
 * contrat (`npm run gen:api` pas encore relancé après une évolution backend).
 */
export const QUARANTINE_REASON_LABELS: Record<QuarantineReason, string> = {
  truncated_file: "Fichier tronqué à l'envoi",
  not_an_image: "Le fichier n'est pas une image exploitable",
  unsupported_mime: "Format de fichier non pris en charge",
  dimensions_out_of_range: "Dimensions de l'image aberrantes",
  aspect_ratio_out_of_range: "Proportions de l'image aberrantes",
  exif_inconsistent: "Métadonnées EXIF incohérentes",
  too_large: "Fichier trop volumineux",
  quota_exceeded: "Quota de stockage du shooting dépassé",
  ingest_failed: "Échec technique pendant l'ingestion",
  orphan_object: "Fichier orphelin détecté en stockage",
};

export function quarantineReasonLabel(reason: string | null | undefined): string {
  if (!reason) return "Motif non renseigné";
  return QUARANTINE_REASON_LABELS[reason as QuarantineReason] ?? `Motif non répertorié (${reason})`;
}

/**
 * Motifs du bac « à rattacher » — vivent dans `attachment_detail.reason`, désormais un
 * vrai enum OpenAPI (`AttachmentDetail.reason` dans le contrat, § `lib/api/types.ts`).
 * Typé `Record<UnattachedReason, string>` : comme `QUARANTINE_REASON_LABELS` ci-dessus,
 * un motif retiré ici (ou ajouté côté backend sans régénération) est désormais une erreur
 * de type, pas un affichage dégradé constaté en intégration.
 *
 * Correction passe d'intégration live J1 : `outside_shooting_window` n'est **jamais** émis
 * par le backend (`pipeline/attach_time.py`) — la vraie clé est `no_matching_window`
 * (constatée en direct sur un média hors fenêtre de shooting). Corrigé pour refléter les
 * trois raisons réellement produites. Voir `implementation.md`.
 */
export const UNATTACHED_REASON_LABELS: Record<UnattachedReason, string> = {
  no_exif_timestamp: "Aucun horodatage EXIF exploitable",
  ambiguous_window: "Plusieurs shootings se chevauchent sur cet horodatage",
  no_matching_window: "Horodatage hors de la plage de tout shooting connu",
};

export function unattachedReasonLabel(detail: unknown): string {
  if (detail && typeof detail === "object" && "reason" in detail) {
    const reason = String((detail as { reason: unknown }).reason);
    return (
      UNATTACHED_REASON_LABELS[reason as UnattachedReason] ??
      `Rattachement automatique impossible (${reason})`
    );
  }
  return "Rattachement automatique impossible — motif non détaillé";
}

/**
 * `ShootingOut.status` — vrai enum OpenAPI (`@enum {string}` dans `schema.d.ts`), typé
 * `Record<ShootingStatus, string>` : même garde-fou de compilation, dérivé directement du
 * contrat généré (comme `QuarantineReason`/`UnattachedReason` ci-dessus depuis leur
 * fermeture de contrat).
 */
export const SHOOTING_STATUS_LABELS: Record<ShootingStatus, string> = {
  planned: "Programmé",
  done: "Réalisé",
};

/** `ClientOut.kind` — même cas : vrai enum OpenAPI, `Record<ClientKind, string>` exhaustif. */
export const CLIENT_KIND_LABELS: Record<ClientKind, string> = {
  team: "Écurie / team",
  driver: "Pilote indépendant",
  sponsor: "Sponsor",
};

/**
 * `OcrCandidateOut.resolution` (J2, §3-J.3) — vrai enum OpenAPI, `Record<OcrResolution,
 * string>` exhaustif (même garde-fou de compilation que `QUARANTINE_REASON_LABELS`).
 * `auto`/`review`/`abstain`/`not_engaged` sont les issues du classement automatique ;
 * `accepted`/`rejected` sont les décisions humaines appliquées depuis `/review`.
 */
export const OCR_RESOLUTION_LABELS: Record<OcrResolution, string> = {
  auto: "Rattaché automatiquement",
  review: "En file de validation",
  abstain: "Confiance trop faible — abstention",
  not_engaged: "Numéro incohérent — absent des engagements",
  accepted: "Validé manuellement",
  rejected: "Rejeté manuellement",
};

/** `CollectionOut.status` — vrai enum OpenAPI, `Record<CollectionStatus, string>` exhaustif. */
export const COLLECTION_STATUS_LABELS: Record<CollectionStatus, string> = {
  draft: "Brouillon",
  published: "Publiée",
  closed: "Clôturée",
};

/** `MediaEngagementOut.source` — vrai enum OpenAPI, `Record<MediaEngagementSource, string>`. */
export const MEDIA_ENGAGEMENT_SOURCE_LABELS: Record<MediaEngagementSource, string> = {
  ocr: "Lecture OCR",
  human: "Rattachement manuel",
};
