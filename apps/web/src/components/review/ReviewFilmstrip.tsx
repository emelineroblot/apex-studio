"use client";

import type { ReviewItem } from "@/lib/api/types";
import type { DecisionMap } from "@/lib/review/batch";
import { AuthImage } from "@/components/media/AuthImage";

/** Liste compacte de navigation (souris) — la souris et le clavier pilotent le même état de
 * focus (§ tâche 1 : « sans quitter le clavier », mais la souris reste utilisable). */
export function ReviewFilmstrip({
  items,
  focusIndex,
  decisions,
  selectedIds,
  onFocus,
  onToggleSelect,
}: {
  items: ReviewItem[];
  focusIndex: number;
  decisions: DecisionMap;
  selectedIds: ReadonlySet<number>;
  onFocus: (index: number) => void;
  onToggleSelect: (candidateId: number) => void;
}) {
  return (
    <ul className="flex gap-2 overflow-x-auto pb-2" role="listbox" aria-label="File de validation">
      {items.map((item, index) => {
        const decision = decisions.get(item.candidate_id);
        const selected = selectedIds.has(item.candidate_id);
        const focused = index === focusIndex;
        return (
          <li key={item.candidate_id} className="shrink-0">
            <div
              role="option"
              aria-selected={focused}
              tabIndex={-1}
              className={`relative h-16 w-24 cursor-pointer overflow-hidden rounded-md border-2 ${
                focused ? "border-accent-600" : selected ? "border-accent-300" : decision ? "border-ink-300" : "border-transparent"
              }`}
              onClick={() => onFocus(index)}
            >
              <AuthImage src={item.media.thumb_url} alt={`Média #${item.media.id}`} className="h-full w-full object-cover" />
              {decision ? (
                <span
                  className={`absolute bottom-0.5 right-0.5 h-2.5 w-2.5 rounded-full ${
                    decision.action === "accept" ? "bg-ok-500" : decision.action === "reject" ? "bg-danger-500" : "bg-accent-500"
                  }`}
                  aria-hidden="true"
                />
              ) : null}
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleSelect(item.candidate_id);
                }}
                aria-label={selected ? `Retirer le média #${item.media.id} de la sélection en lot` : `Marquer le média #${item.media.id} pour un lot`}
                className="absolute left-0.5 top-0.5 flex h-4 w-4 items-center justify-center rounded bg-white/90 text-[10px]"
              >
                {selected ? "✓" : ""}
              </button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
