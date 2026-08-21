"use client";

import { useId } from "react";
import type { AttachmentStatus, FacetStatusTerm } from "@/lib/api/types";
import { ATTACHMENT_STATUS_LABELS } from "@/lib/labels";

/** Facette « statut » (`attachment_status`) — libellés dérivés du contrat comme partout
 * ailleurs (`lib/labels.ts`), jamais recopiés. */
export function FacetStatusGroup({
  terms,
  selected,
  onChange,
}: {
  terms: FacetStatusTerm[];
  selected: AttachmentStatus[];
  onChange: (next: AttachmentStatus[]) => void;
}) {
  const groupId = useId();
  if (terms.length === 0) return null;
  const selectedSet = new Set(selected);

  function toggle(value: AttachmentStatus) {
    onChange(selectedSet.has(value) ? selected.filter((v) => v !== value) : [...selected, value]);
  }

  return (
    <fieldset className="border-t border-ink-100 pt-3 first:border-t-0 first:pt-0">
      <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">Statut</legend>
      <ul className="flex flex-col gap-1.5">
        {terms.map((term) => {
          const value = term.value as AttachmentStatus;
          const inputId = `${groupId}-${value}`;
          const disabled = term.count === 0 && !selectedSet.has(value);
          return (
            <li key={value}>
              <label
                htmlFor={inputId}
                className="flex cursor-pointer items-center justify-between gap-2 text-sm text-ink-700 aria-disabled:cursor-default aria-disabled:text-ink-300"
                aria-disabled={disabled}
              >
                <span className="flex items-center gap-2">
                  <input
                    id={inputId}
                    type="checkbox"
                    checked={selectedSet.has(value)}
                    disabled={disabled}
                    onChange={() => toggle(value)}
                    className="h-4 w-4 rounded border-ink-300 text-accent-600 focus-visible:outline-2 focus-visible:outline-accent-600"
                  />
                  {ATTACHMENT_STATUS_LABELS[value] ?? value}
                </span>
                <span className="tabular-nums text-xs text-ink-400">{term.count}</span>
              </label>
            </li>
          );
        })}
      </ul>
    </fieldset>
  );
}
