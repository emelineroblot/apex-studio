import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { QUARANTINE_DETAIL_KEYS } from "@/lib/api/types";

/**
 * `QuarantineCard.DETAIL_LABELS` n'est pas exporté (composant React, coûteux à monter
 * juste pour lire une constante) — ce test lit le **code source réel** plutôt que de
 * dupliquer la constante à la main, pour rester vrai même si le fichier change de forme.
 *
 * Contrat vérifié : chaque clé que le backend écrit effectivement dans
 * `media.quarantine_detail` a un libellé français dans `DETAIL_LABELS` — sinon
 * `QuarantineCard` affiche la clé technique brute (`detail[key] ?? key`), ce que
 * l'invariant du composant interdit explicitement. C'est exactement la classe de
 * régression déjà trouvée **trois fois** en intégration live J1 (`implementation.md`).
 *
 * Depuis la correction de ce lot, `DETAIL_LABELS` est aussi typé
 * `Record<QuarantineDetailKey, string>` (§ `lib/api/types.ts`) — une clé listée dans
 * `QUARANTINE_DETAIL_KEYS` sans libellé échoue désormais à la **compilation**
 * (`npm run typecheck`), avant même d'arriver jusqu'ici. Ce test reste utile en défense
 * seconde : il attrape aussi un DETAIL_LABELS qui ne serait plus typé `Record<...>` (ex.
 * un futur refactor qui repasserait par erreur à `Record<string, string>`).
 *
 * ⚠️ Replacé dans `components/media/` : `.gitignore` a été corrigé (motifs ancrés à la
 * racine, § racine du dépôt) — ce dossier n'est plus ignoré, voir `implementation.md`.
 */

const COMPONENT_PATH = resolve(dirname(fileURLToPath(import.meta.url)), "QuarantineCard.tsx");

// Source de vérité unique pour les clés du contrat : `QUARANTINE_DETAIL_KEYS`
// (`lib/api/types.ts`), dérivée du schéma `QuarantineDetail` généré depuis
// `services/api/openapi.json` (`npm run gen:api`), lui-même issu de
// `apex.models.media.QUARANTINE_DETAIL_KEYS` côté backend (verrouillé dans les deux sens
// par `services/api/tests/test_openapi_contract.py`).
const BACKEND_QUARANTINE_DETAIL_KEYS = QUARANTINE_DETAIL_KEYS;

function extractDetailLabelKeys(): string[] {
  const source = readFileSync(COMPONENT_PATH, "utf-8");
  const match = source.match(/const DETAIL_LABELS: Record<QuarantineDetailKey, string> = \{([\s\S]*?)\};/);
  if (!match) {
    throw new Error(
      "DETAIL_LABELS introuvable dans QuarantineCard.tsx — le composant a changé de forme, " +
        "ce test doit être adapté (pas supprimé) avant d'être considéré comme couvrant.",
    );
  }
  const body = match[1];
  return [...body.matchAll(/^\s*([A-Za-z0-9_]+):\s*"/gm)].map((m) => m[1]);
}

describe("QuarantineCard DETAIL_LABELS (contrat statique)", () => {
  it("a un libellé pour chaque clé de quarantine_detail réellement émise par le backend", () => {
    const keys = extractDetailLabelKeys();
    const missing = BACKEND_QUARANTINE_DETAIL_KEYS.filter((k) => !keys.includes(k));
    expect(
      missing,
      `clés sans libellé français : ${missing.join(", ")} — QuarantineCard afficherait le ` +
        "code technique brut pour ces champs, en violation de l'invariant du composant",
    ).toEqual([]);
  });
});
