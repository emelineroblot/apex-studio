"use client";

import clsx from "clsx";
import type { FacetBucket } from "@/lib/api/types";

/**
 * Plage ISO/focale — histogramme **cliquable** (§ tâche 3 : « plages d'ISO et de focale »).
 * Un clic sur une barre pose `[from, to]` comme filtre exact de cette tranche ; un second
 * clic sur la même barre l'efface. Mono-sélection : une seule tranche active à la fois,
 * cohérent avec `iso_min`/`iso_max` (deux bornes, pas une liste) du contrat.
 */
export function FacetBucketList({
  legend,
  buckets,
  unit,
  activeMin,
  activeMax,
  onChange,
}: {
  legend: string;
  buckets: FacetBucket[];
  unit: string;
  activeMin: number | null;
  activeMax: number | null;
  onChange: (range: { min: number | null; max: number | null }) => void;
}) {
  if (buckets.length === 0 || buckets.every((b) => b.count === 0)) return null;
  const max = Math.max(...buckets.map((b) => b.count), 1);

  // `FacetBucket.from_` : nom de champ réel du contrat (§ `lib/search/engine.ts`, alias
  // Python `from` → `from_`, non renommé côté OpenAPI).
  function bucketLabel(bucket: FacetBucket): string {
    if (bucket.from_ == null) return `< ${bucket.to} ${unit}`;
    if (bucket.to == null) return `≥ ${bucket.from_} ${unit}`;
    return `${bucket.from_}-${bucket.to} ${unit}`;
  }

  function isActive(bucket: FacetBucket): boolean {
    return (bucket.from_ ?? null) === activeMin && (bucket.to ?? null) === activeMax;
  }

  return (
    <fieldset className="border-t border-ink-100 pt-3 first:border-t-0 first:pt-0">
      <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">{legend}</legend>
      <ul className="flex flex-col gap-1">
        {buckets.map((bucket, idx) => {
          const active = isActive(bucket);
          return (
            <li key={idx}>
              <button
                type="button"
                onClick={() => onChange(active ? { min: null, max: null } : { min: bucket.from_ ?? null, max: bucket.to ?? null })}
                disabled={bucket.count === 0 && !active}
                aria-pressed={active}
                className={clsx(
                  "group flex w-full items-center gap-2 rounded px-1 py-0.5 text-left text-xs focus-visible:outline-2 focus-visible:outline-accent-600",
                  active ? "text-accent-700 font-medium" : "text-ink-600 hover:text-ink-900",
                  bucket.count === 0 && !active && "cursor-not-allowed text-ink-300",
                )}
              >
                <span className="w-20 shrink-0 tabular-nums">{bucketLabel(bucket)}</span>
                <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-ink-100">
                  <span
                    className={clsx("block h-full rounded-full", active ? "bg-accent-600" : "bg-ink-300 group-hover:bg-ink-400")}
                    style={{ width: `${Math.max(4, (bucket.count / max) * 100)}%` }}
                  />
                </span>
                <span className="w-6 shrink-0 text-right tabular-nums">{bucket.count}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </fieldset>
  );
}
