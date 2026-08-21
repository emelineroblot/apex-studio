import { describe, expect, it } from "vitest";
import { computeDistribution, computePreviewDistribution, reclassifyResolution } from "@/lib/ocr/reclassify";

const THRESHOLDS = { high: 0.8, low: 0.45 };

describe("lib/ocr/reclassify — reclassement sans ré-inférence (§3-J.4)", () => {
  it("un candidat sans engagement trouvé reste `not_engaged`, quel que soit le score", () => {
    expect(
      reclassifyResolution({ confidence: 0.99, engagement_id: null, resolution: "not_engaged" }, THRESHOLDS),
    ).toBe("not_engaged");
    // Même avec des seuils très permissifs — jamais rattaché de force (critère d'acceptation).
    expect(
      reclassifyResolution({ confidence: 0.99, engagement_id: null, resolution: "not_engaged" }, { high: 0.01, low: 0 }),
    ).toBe("not_engaged");
  });

  it("un candidat déjà tranché par un humain (accepted/rejected) n'est jamais rejoué", () => {
    expect(reclassifyResolution({ confidence: 0.1, engagement_id: 1, resolution: "accepted" }, THRESHOLDS)).toBe("accepted");
    expect(reclassifyResolution({ confidence: 0.99, engagement_id: 1, resolution: "rejected" }, THRESHOLDS)).toBe("rejected");
  });

  it("un candidat avec engagement trouvé se répartit selon le seul score", () => {
    expect(reclassifyResolution({ confidence: 0.85, engagement_id: 1, resolution: "review" }, THRESHOLDS)).toBe("auto");
    expect(reclassifyResolution({ confidence: 0.6, engagement_id: 1, resolution: "review" }, THRESHOLDS)).toBe("review");
    expect(reclassifyResolution({ confidence: 0.3, engagement_id: 1, resolution: "auto" }, THRESHOLDS)).toBe("abstain");
  });

  it("changer les seuils redistribue les cas — même candidat, verdict différent", () => {
    const candidate = { confidence: 0.6, engagement_id: 1, resolution: "review" as const };
    expect(reclassifyResolution(candidate, { high: 0.8, low: 0.45 })).toBe("review");
    expect(reclassifyResolution(candidate, { high: 0.5, low: 0.45 })).toBe("auto"); // seuil haut abaissé sous 0.6
    expect(reclassifyResolution(candidate, { high: 0.8, low: 0.65 })).toBe("abstain"); // seuil bas relevé au-dessus de 0.6
  });
});

describe("lib/ocr/reclassify — distribution", () => {
  const candidates = [
    { confidence: 0.9, engagement_id: 1, resolution: "auto" as const },
    { confidence: 0.6, engagement_id: 2, resolution: "review" as const },
    { confidence: 0.2, engagement_id: 3, resolution: "abstain" as const },
    { confidence: 0.95, engagement_id: null, resolution: "not_engaged" as const },
    { confidence: 0.5, engagement_id: 4, resolution: "accepted" as const }, // tranché, hors distribution
  ];

  it("computeDistribution exclut les candidats déjà tranchés par un humain", () => {
    const distribution = computeDistribution(candidates, THRESHOLDS);
    expect(distribution).toEqual({ auto: 1, review: 1, abstain: 1, not_engaged: 1 });
  });

  it("computePreviewDistribution n'expose jamais `not_engaged` — ce bac ne bouge pas avec les seuils", () => {
    const preview = computePreviewDistribution(candidates, THRESHOLDS);
    expect(preview).toEqual({ auto: 1, review: 1, abstain: 1 });
    expect("not_engaged" in preview).toBe(false);
  });
});
