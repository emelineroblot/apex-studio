"use client";

import { useId, useState } from "react";
import type { FacetTerm } from "@/lib/api/types";
import { hashStringId, missingSelectedTerms } from "@/lib/search/facetSelection";

/**
 * Variante textuelle de `FacetCheckboxGroup` — pour les facettes dont la valeur de filtre
 * **est** la chaîne affichée (`car_number`, `lens`) : `FacetTerm.id` y est un hash
 * déterministe sans signification (le contrat impose `id: int` même pour ces deux
 * facettes textuelles côté fixtures, § `lib/search/engine.ts::hashStringId`), donc on
 * sélectionne par `label`, jamais par `id`.
 *
 * Revue J2 🟡14 — même correction que `FacetCheckboxGroup` : une valeur sélectionnée hors
 * du top 50 renvoyé par le backend (`FACET_TERM_LIMIT`) est toujours réinjectée. Ici, à la
 * différence de la variante numérique, le libellé métier **est** la valeur du filtre
 * elle-même (`selected` porte directement la chaîne affichable) — pas de repli générique
 * nécessaire.
 */
export function FacetCheckboxGroupText({
  legend,
  terms,
  selected,
  onChange,
  collapseAfter = 6,
}: {
  legend: string;
  terms: FacetTerm[];
  selected: string[];
  onChange: (next: string[]) => void;
  collapseAfter?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const groupId = useId();
  if (terms.length === 0 && selected.length === 0) return null;

  const missing = missingSelectedTerms(terms, selected, (t, label) => t.label === label, (label) => ({
    id: hashStringId(label),
    label,
    count: 0,
  }));
  const visible = [...(expanded ? terms : terms.slice(0, collapseAfter)), ...missing];
  const selectedSet = new Set(selected);

  function toggle(label: string) {
    onChange(selectedSet.has(label) ? selected.filter((v) => v !== label) : [...selected, label]);
  }

  return (
    <fieldset className="border-t border-ink-100 pt-3 first:border-t-0 first:pt-0">
      <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">{legend}</legend>
      <ul className="flex flex-col gap-1.5">
        {visible.map((term) => {
          const inputId = `${groupId}-${term.id}`;
          const disabled = term.count === 0 && !selectedSet.has(term.label);
          return (
            <li key={term.label}>
              <label
                htmlFor={inputId}
                className="flex cursor-pointer items-center justify-between gap-2 text-sm text-ink-700 aria-disabled:cursor-default aria-disabled:text-ink-300"
                aria-disabled={disabled}
              >
                <span className="flex items-center gap-2">
                  <input
                    id={inputId}
                    type="checkbox"
                    checked={selectedSet.has(term.label)}
                    disabled={disabled}
                    onChange={() => toggle(term.label)}
                    className="h-4 w-4 rounded border-ink-300 text-accent-600 focus-visible:outline-2 focus-visible:outline-accent-600"
                  />
                  <span className="max-w-[13rem] truncate" title={term.label}>
                    {term.label}
                  </span>
                </span>
                <span className="tabular-nums text-xs text-ink-400">{term.count}</span>
              </label>
            </li>
          );
        })}
      </ul>
      {terms.length > collapseAfter ? (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-1.5 text-xs font-medium text-accent-600 hover:underline focus-visible:outline-2 focus-visible:outline-accent-600 focus-visible:outline-offset-1"
        >
          {expanded ? "Voir moins" : `Voir tout (${terms.length})`}
        </button>
      ) : null}
    </fieldset>
  );
}
