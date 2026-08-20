import Link from "next/link";
import type { MediaOut, QuarantineDetailKey } from "@/lib/api/types";
import { quarantineReasonLabel } from "@/lib/labels";
import { formatBytes, formatDateTime } from "@/lib/format";
import { AuthImage } from "@/components/media/AuthImage";
import { Card } from "@/components/ui/Card";

/** Motif **toujours** traduit en français — jamais le code technique brut (invariant `AGENTS.md`). */
export function QuarantineCard({ media, thumbUrl }: { media: MediaOut; thumbUrl: string }) {
  const detail = media.quarantine_detail as Record<string, unknown> | null;

  return (
    <Card className="flex gap-4">
      <Link href={`/media/${media.id}`} className="shrink-0">
        <div className="h-20 w-28 overflow-hidden rounded-lg bg-ink-100">
          <AuthImage src={thumbUrl} alt={`Média #${media.id}`} className="h-full w-full object-cover" />
        </div>
      </Link>
      <div className="flex-1">
        <div className="flex items-start justify-between gap-3">
          <div>
            <Link href={`/media/${media.id}`} className="text-sm font-semibold text-ink-900 hover:text-accent-600">
              {media.original_filename}
            </Link>
            <p className="mt-0.5 text-sm font-medium text-danger-600">{quarantineReasonLabel(media.quarantine_reason)}</p>
          </div>
          <span className="shrink-0 text-xs text-ink-400">{formatBytes(media.byte_size)}</span>
        </div>

        {detail ? (
          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-ink-600 sm:grid-cols-3">
            {Object.entries(detail).map(([key, value]) => (
              <div key={key} className="flex justify-between gap-2 sm:justify-start">
                <dt className="text-ink-400">{DETAIL_LABELS[key as QuarantineDetailKey] ?? key}</dt>
                <dd className="font-medium">{formatDetailValue(key, value)}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        <p className="mt-2 text-xs text-ink-400">Déposé le {formatDateTime(media.shot_at_exif ?? undefined)}</p>
      </div>
    </Card>
  );
}

/**
 * Correction passe d'intégration live J1 : les clés ci-dessous rejouent fidèlement
 * `quarantine_detail` tel que réellement produit par le backend (§ `pipeline/integrity.py`,
 * `routers/batches.py`) — `bytes_read`/`bytes_expected`/`min_expected` de la première
 * version n'étaient jamais émis par l'API ; `expected`/`ratio`/`error`/`format`/`byte_size`
 * l'sont et tombaient donc en repli sur la clé technique brute (`detail[key] ?? key`),
 * ce que l'invariant de ce composant interdit. Voir `implementation.md`.
 *
 * **Troisième régression de la même classe** (`shot_at_exif` manquant, trouvée par
 * `dev-tester` sur ce lot) — traitée à la cause plutôt qu'au symptôme : ce dictionnaire est
 * maintenant typé `Record<QuarantineDetailKey, string>` (§ `lib/api/types.ts`). Retirer une
 * entrée ci-dessous est désormais une **erreur de type** (`tsc`/`npm run typecheck`), pas un
 * défaut d'affichage constaté en intégration. Cinq autres clés réellement émises par le
 * backend étaient elles aussi absentes (`step`, `reason`, `last_error`, `storage_key`,
 * `found_at` — motifs `ingest_failed` et `orphan_object`, jamais couverts par les deux
 * corrections précédentes) : ajoutées dans le même mouvement.
 *
 * ⚠️ Cette exhaustivité ne protège que contre l'oubli d'une clé déjà listée dans
 * `QuarantineDetailKey` — si le backend en introduit une nouvelle sans que quelqu'un mette
 * à jour ce mirroir manuel (le contrat OpenAPI ne l'exposera jamais, `quarantine_detail` y
 * est JSON libre, voir `types.ts`), rien ne le détecte à la compilation. Un test source
 * (`QuarantineCard.detail-labels.test.ts`) et la revue restent la seule protection pour ce
 * cas-là.
 */
const DETAIL_LABELS: Record<QuarantineDetailKey, string> = {
  width: "Largeur mesurée",
  height: "Hauteur mesurée",
  expected: "Plage attendue",
  ratio: "Ratio mesuré",
  format: "Format détecté",
  error: "Erreur de lecture",
  byte_size: "Taille du fichier",
  max_upload_bytes: "Taille maximale autorisée",
  used_bytes: "Déjà utilisé sur le quota",
  incoming_bytes: "Taille du fichier envoyé",
  quota_bytes: "Quota du shooting",
  shot_at_exif: "Date de prise de vue (EXIF)",
  step: "Étape du pipeline en échec",
  reason: "Motif technique",
  last_error: "Dernière erreur (file de tâches)",
  storage_key: "Clé de stockage",
  found_at: "Détecté le",
};

/** Clés portant un nombre d'octets — plus lisible en « 6,2 Mo » qu'en `6200000` brut. */
const BYTE_DETAIL_KEYS = new Set<QuarantineDetailKey>([
  "byte_size",
  "max_upload_bytes",
  "used_bytes",
  "incoming_bytes",
  "quota_bytes",
]);

/** Clés portant un horodatage ISO — affichées en date française plutôt qu'en ISO brut. */
const DATE_DETAIL_KEYS = new Set<QuarantineDetailKey>(["shot_at_exif", "found_at"]);

function formatDetailValue(key: string, value: unknown): string {
  const typedKey = key as QuarantineDetailKey;
  if (BYTE_DETAIL_KEYS.has(typedKey) && typeof value === "number") return formatBytes(value);
  if (DATE_DETAIL_KEYS.has(typedKey) && typeof value === "string") return formatDateTime(value);
  if ((typedKey === "width" || typedKey === "height") && typeof value === "number") return `${value} px`;
  return String(value);
}
