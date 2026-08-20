/**
 * Dictionnaires de libellés français — un motif technique n'est **jamais** affiché tel
 * quel à l'écran (invariant `AGENTS.md` : bac explicite, motif lisible).
 */
import type {
  AttachmentStatus,
  ClientKind,
  IngestStatus,
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
 * §3-F.2 du plan, énumération fermée `QUARANTINE_REASONS` de `apex/models/media.py`.
 * Toute valeur inconnue (contrat qui évoluerait) retombe sur un libellé générique plutôt
 * que d'afficher le code technique brut.
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
 * Motifs du bac « à rattacher » — vivent dans `attachment_detail.reason` (JSON libre côté
 * backend, non typé dans l'OpenAPI — voir `UnattachedReason` dans `lib/api/types.ts` pour
 * le détail du trou de contrat). Typé `Record<UnattachedReason, string>` : comme
 * `QUARANTINE_REASON_LABELS` ci-dessus, un motif retiré ici est désormais une erreur de
 * type, pas un affichage dégradé à l'exécution.
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
 * `ShootingOut.status` **est** un vrai enum OpenAPI (`@enum {string}` dans `schema.d.ts`,
 * contrairement à `quarantine_reason`/`attachment_detail.reason` ci-dessus) — typé
 * `Record<ShootingStatus, string>` : ici, le garde-fou de compilation est directement
 * dérivé du contrat généré, pas d'un mirroir manuel.
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
