import { describe, expect, it } from "vitest";
import {
  QUARANTINE_REASON_LABELS,
  UNATTACHED_REASON_LABELS,
  quarantineReasonLabel,
  unattachedReasonLabel,
} from "@/lib/labels";

/**
 * Deux régressions ont déjà été trouvées en intégration live J1 (`implementation.md`,
 * section « Intégration live J1 ») parce que les dictionnaires de libellés français ne
 * correspondaient pas aux **clés réellement émises par le backend** :
 * - `UNATTACHED_REASON_LABELS` contenait `outside_shooting_window`, jamais émis
 *   (`pipeline/attach_time.py` émet `no_matching_window`) ;
 * - `QuarantineCard.DETAIL_LABELS` attendait `bytes_read`/`bytes_expected`/`min_expected`,
 *   jamais émis (`pipeline/integrity.py`, `routers/batches.py`).
 *
 * Ce test fige, côté frontend, la liste des clés que le backend émet réellement — relue
 * directement dans le code source Python à la date de ce lot (pas copiée depuis un
 * commentaire) — pour que toute divergence future échoue ici plutôt qu'en intégration.
 */

// `apex.models.media.QUARANTINE_REASONS` (services/api/src/apex/models/media.py).
const BACKEND_QUARANTINE_REASONS = [
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

// Motifs réellement écrits dans `media.attachment_detail.reason` par le pipeline
// (`pipeline/attach_time.py::attach_media_by_time`) : `no_exif_timestamp`,
// `no_matching_window`, `ambiguous_window`. `outside_shooting_window` n'existe nulle part
// côté backend — sa présence ici serait la régression déjà trouvée une fois.
const BACKEND_UNATTACHED_REASONS = [
  "no_exif_timestamp",
  "no_matching_window",
  "ambiguous_window",
] as const;

describe("QUARANTINE_REASON_LABELS", () => {
  it("couvre chaque motif de l'énumération fermée du backend", () => {
    for (const reason of BACKEND_QUARANTINE_REASONS) {
      expect(QUARANTINE_REASON_LABELS, `motif « ${reason} » sans libellé`).toHaveProperty(reason);
      expect(QUARANTINE_REASON_LABELS[reason]).not.toMatch(/^[a-z_]+$/); // pas un code brut
    }
  });

  it("ne contient aucune clé obsolète que le backend n'émet plus", () => {
    const known = new Set<string>(BACKEND_QUARANTINE_REASONS);
    for (const key of Object.keys(QUARANTINE_REASON_LABELS)) {
      expect(known.has(key), `clé « ${key} » absente de l'énumération backend`).toBe(true);
    }
  });

  it("quarantineReasonLabel ne renvoie jamais le code technique brut tel quel", () => {
    for (const reason of BACKEND_QUARANTINE_REASONS) {
      expect(quarantineReasonLabel(reason)).not.toBe(reason);
    }
  });

  it("quarantineReasonLabel a un repli lisible sur un motif inconnu (contrat qui évoluerait)", () => {
    expect(quarantineReasonLabel("un_motif_jamais_vu")).toContain("un_motif_jamais_vu");
    expect(quarantineReasonLabel(null)).toBe("Motif non renseigné");
    expect(quarantineReasonLabel(undefined)).toBe("Motif non renseigné");
  });
});

describe("UNATTACHED_REASON_LABELS", () => {
  it("couvre chaque motif réellement émis par pipeline/attach_time.py", () => {
    for (const reason of BACKEND_UNATTACHED_REASONS) {
      expect(UNATTACHED_REASON_LABELS, `motif « ${reason} » sans libellé`).toHaveProperty(reason);
    }
  });

  it("ne contient plus la clé « outside_shooting_window » (régression déjà corrigée)", () => {
    expect(UNATTACHED_REASON_LABELS).not.toHaveProperty("outside_shooting_window");
  });

  it("unattachedReasonLabel traduit chaque motif réel en libellé français lisible", () => {
    for (const reason of BACKEND_UNATTACHED_REASONS) {
      const label = unattachedReasonLabel({ reason });
      expect(label).not.toBe(reason);
      expect(label.length).toBeGreaterThan(0);
    }
  });

  it("unattachedReasonLabel a un repli sur un detail absent ou mal formé", () => {
    expect(unattachedReasonLabel(null)).toContain("non détaillé");
    expect(unattachedReasonLabel(undefined)).toContain("non détaillé");
    expect(unattachedReasonLabel({ reason: "un_motif_jamais_vu" })).toContain("un_motif_jamais_vu");
  });
});
