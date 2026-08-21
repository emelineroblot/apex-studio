"use client";

import { useId, useState } from "react";
import type { FacetTerm } from "@/lib/api/types";
import { missingSelectedTerms } from "@/lib/search/facetSelection";

/**
 * Groupe de cases à cocher avec **compteur par option** (§3-K.2 — les compteurs reflètent
 * tous les filtres actifs sauf celui-ci, calculés côté `lib/search/engine.ts`/backend).
 * Une facette à zéro résultat reste affichée mais grisée : décocher un filtre pour la
 * retrouver doit rester possible sans qu'elle disparaisse de la liste (piège classique des
 * panneaux de facettes qui « sautent »).
 *
 * Revue J2 🟡14 — `terms` est tronqué côté backend (`FACET_TERM_LIMIT = 50`, par volume). Un
 * filtre **actif** dont l'id ne fait pas partie de ce top 50 n'apparaîtrait plus du tout ici
 * et deviendrait impossible à décocher autrement qu'en réinitialisant tous les filtres. Les
 * valeurs sélectionnées absentes de `terms` sont donc toujours réinjectées, quelle que soit
 * leur position — sans libellé métier disponible à ce niveau (le panneau ne reçoit que des
 * ids), affichées avec un repli honnête plutôt qu'un libellé inventé.
 */
export function FacetCheckboxGroup({
  legend,
  terms,
  selected,
  onChange,
  collapseAfter = 6,
}: {
  legend: string;
  terms: FacetTerm[];
  selected: number[];
  onChange: (next: number[]) => void;
  collapseAfter?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const groupId = useId();
  if (terms.length === 0 && selected.length === 0) return null;

  const missing = missingSelectedTerms(terms, selected, (t, id) => t.id === id, (id) => ({
    id,
    label: `Filtre actif (#${id})`,
    count: 0,
  }));
  const visible = [...(expanded ? terms : terms.slice(0, collapseAfter)), ...missing];
  const selectedSet = new Set(selected);

  function toggle(id: number) {
    onChange(selectedSet.has(id) ? selected.filter((v) => v !== id) : [...selected, id]);
  }

  return (
    <fieldset className="border-t border-ink-100 pt-3 first:border-t-0 first:pt-0">
      <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">{legend}</legend>
      <ul className="flex flex-col gap-1.5">
        {visible.map((term) => {
          const inputId = `${groupId}-${term.id}`;
          const disabled = term.count === 0 && !selectedSet.has(term.id);
          return (
            <li key={term.id}>
              <label
                htmlFor={inputId}
                className="flex cursor-pointer items-center justify-between gap-2 text-sm text-ink-700 aria-disabled:cursor-default aria-disabled:text-ink-300"
                aria-disabled={disabled}
              >
                <span className="flex items-center gap-2">
                  <input
                    id={inputId}
                    type="checkbox"
                    checked={selectedSet.has(term.id)}
                    disabled={disabled}
                    onChange={() => toggle(term.id)}
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
