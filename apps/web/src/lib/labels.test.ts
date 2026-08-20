import { describe, expect, it } from "vitest";
import { QUARANTINE_REASONS, UNATTACHED_REASONS } from "@/lib/api/types";
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
 * `quarantine_reason` et `attachment_detail.reason` sont désormais de vrais enums du
 * contrat OpenAPI (§ « Correction de suivi — Contrat OpenAPI des motifs de quarantaine/
 * rattachement », `implementation.md`) : `QUARANTINE_REASONS`/`UNATTACHED_REASONS`
 * (`lib/api/types.ts`) sont dérivées de `schema.d.ts` (généré, `npm run gen:api`), pas
 * recopiées à la main ici — ce test ne duplique donc plus une liste indépendante, il
 * confronte les dictionnaires de libellés à la liste réellement issue du contrat.
 */
const BACKEND_QUARANTINE_REASONS = QUARANTINE_REASONS;
const BACKEND_UNATTACHED_REASONS = UNATTACHED_REASONS;

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
