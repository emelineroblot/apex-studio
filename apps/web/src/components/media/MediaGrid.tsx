import Link from "next/link";
import type { MediaSummary } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { AuthImage } from "@/components/media/AuthImage";
import { IngestStatusBadge, SimulatedBadge } from "@/components/media/StatusBadges";

/** Construit l'URL d'ouverture d'une série complète — consommée par `library/page.tsx`
 * (§ « série collapsée » du contrat `GET /media?series=all`, pas de paramètre `series_id`
 * dédié : filtre appliqué côté client sur les membres de la série, cf. `resources/media.ts`). */
export function seriesUrl(seriesId: number, shootingId: number | null): string {
  const params = new URLSearchParams({ series: String(seriesId) });
  if (shootingId != null) params.set("shooting", String(shootingId));
  return `/library?${params.toString()}`;
}

export function MediaGrid({
  items,
  showSeriesBadge = true,
  selectable = false,
  selectedIds,
  onToggleSelect,
}: {
  items: MediaSummary[];
  /** `false` dans la vue « série complète » (`library/page.tsx?series=…`) — sinon chaque
   * membre affiche un lien « Rafale · N » qui rouvre la série depuis l'intérieur d'elle-même. */
  showSeriesBadge?: boolean;
  /** `true` sur `/search` (§ tâche 4 — composer une collection depuis une sélection) : affiche
   * une case à cocher par vignette, la navigation vers la fiche média reste possible. */
  selectable?: boolean;
  selectedIds?: ReadonlySet<number>;
  /** `index` de l'item dans `items` (pas son id) — nécessaire au `Shift`+clic
   * (`lib/search/selection.ts::toggleWithRange`), l'événement natif porte `shiftKey`. */
  onToggleSelect?: (index: number, event: { shiftKey: boolean }) => void;
}) {
  return (
    <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
      {items.map((item, index) => {
        const isSeriesRepresentative =
          showSeriesBadge && item.series_id != null && (item.series_member_count ?? 0) > 1;
        const isSelected = selectable && (selectedIds?.has(item.id) ?? false);
        return (
          <li key={item.id}>
            <div
              className={`group relative overflow-hidden rounded-lg border bg-white transition-shadow hover:shadow-md ${
                isSelected ? "border-accent-600 ring-2 ring-accent-600/40" : "border-ink-100"
              }`}
            >
              {selectable ? (
                <label
                  className="absolute left-1.5 top-1.5 z-10 flex h-5 w-5 cursor-pointer items-center justify-center rounded bg-white/90 shadow"
                  onClick={(e) => e.stopPropagation()}
                >
                  <span className="sr-only">Sélectionner le média #{item.id}</span>
                  <input
                    type="checkbox"
                    checked={isSelected}
                    readOnly
                    onClick={(e) => onToggleSelect?.(index, { shiftKey: e.shiftKey })}
                    className="h-4 w-4 rounded border-ink-300 text-accent-600 focus-visible:outline-2 focus-visible:outline-accent-600"
                  />
                </label>
              ) : null}
              <Link
                href={`/media/${item.id}`}
                className="block focus-visible:outline-2 focus-visible:outline-accent-600 focus-visible:outline-offset-2"
              >
                <div className="relative aspect-[3/2] w-full overflow-hidden bg-ink-100">
                  <AuthImage
                    src={item.thumb_url}
                    alt={`Média #${item.id}${item.shot_at ? `, pris le ${formatDateTime(item.shot_at)}` : ""}`}
                    className="h-full w-full object-cover transition-transform group-hover:scale-[1.03]"
                  />
                  {item.duplicate_of_media_id != null ? (
                    <span className="absolute left-1.5 top-1.5 rounded bg-ink-950/80 px-1.5 py-0.5 text-[10px] font-medium text-white">
                      Doublon de #{item.duplicate_of_media_id}
                    </span>
                  ) : null}
                </div>
                <div className="flex items-center justify-between gap-1 px-2 py-1.5">
                  <span className="truncate text-xs text-ink-500">
                    {item.shot_at ? formatDateTime(item.shot_at) : "Horodatage inconnu"}
                  </span>
                  <span className="flex shrink-0 items-center gap-1">
                    {item.is_simulated ? <SimulatedBadge /> : null}
                    <IngestStatusBadge status={item.ingest_status} />
                  </span>
                </div>
              </Link>
              {isSeriesRepresentative ? (
                <Link
                  href={seriesUrl(item.series_id as number, item.shooting_id)}
                  className="absolute right-1.5 top-1.5 rounded bg-accent-600/90 px-1.5 py-0.5 text-[10px] font-medium text-white hover:bg-accent-700 focus-visible:outline-2 focus-visible:outline-white focus-visible:outline-offset-1"
                  aria-label={`Voir les ${item.series_member_count} clichés de cette rafale`}
                >
                  Rafale · {item.series_member_count}
                </Link>
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
