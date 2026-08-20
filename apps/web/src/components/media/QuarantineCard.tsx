import Link from "next/link";
import type { MediaOut, QuarantineDetailKey } from "@/lib/api/types";
import { quarantineReasonLabel } from "@/lib/labels";
import { formatBytes, formatDateTime } from "@/lib/format";
import { AuthImage } from "@/components/media/AuthImage";
import { Card } from "@/components/ui/Card";

/** Motif **toujours** traduit en français — jamais le code technique brut (invariant `AGENTS.md`). */
export function QuarantineCard({ media, thumbUrl }: { media: MediaOut; thumbUrl: string }) {
  // `media.quarantine_detail` est désormais le modèle généré `QuarantineDetail` (§ `lib/api/
  // types.ts`), pas un dict libre : plus de cast. Pydantic (`QuarantineDetail.model_validate`,
  // `routers/media.py::_quarantine_detail`) remplit les 17 clés du schéma, la plupart à `null`
  // pour un motif donné (une seule poignée de clés est réellement pertinente par motif) — sans
  // filtrage, la carte afficherait une dizaine de lignes « null » en plus des valeurs utiles.
  // On ne garde donc que les entrées effectivement renseignées, comme le faisait déjà
  // implicitement l'ancien dict JSONB partiel (qui n'avait jamais ces clés en premier lieu).
  const detail = media.quarantine_detail;
  const detailEntries = detail
    ? Object.entries(detail).filter(([, value]) => value !== null && value !== undefined)
    : [];

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

        {detailEntries.length > 0 ? (
          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-ink-600 sm:grid-cols-3">
            {detailEntries.map(([key, value]) => (
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
 * `quarantine_detail` est désormais un vrai schéma fermé du contrat OpenAPI
 * (`QuarantineDetail`, § `lib/api/types.ts`, `QuarantineDetailKey = keyof
 * QuarantineDetail`) : une clé retirée du contrat sans être retirée d'ici est une erreur
 * de type, **et** une clé ajoutée au contrat sans être reportée ici en est une aussi (via
 * le `satisfies Record<QuarantineDetailKey, true>` de `QUARANTINE_DETAIL_KEYS`) — les deux
 * sens de la régression trouvée trois fois en intégration live J1 sont donc désormais
 * fermés par le compilateur, pas seulement le premier. `QuarantineCard.detail-labels.test.ts`
 * reste une défense seconde utile si `DETAIL_LABELS` perdait un jour son typage `Record<...>`.
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
