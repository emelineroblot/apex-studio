"use client";

import clsx from "clsx";

export type TabItem = { id: string; label: string; badge?: React.ReactNode };

export function Tabs({
  items,
  active,
  onChange,
  label,
}: {
  items: TabItem[];
  active: string;
  onChange: (id: string) => void;
  label: string;
}) {
  return (
    <div role="tablist" aria-label={label} className="flex flex-wrap gap-1 border-b border-ink-100">
      {items.map((item) => {
        const selected = item.id === active;
        return (
          <button
            key={item.id}
            role="tab"
            type="button"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(item.id)}
            className={clsx(
              "flex items-center gap-2 border-b-2 px-3.5 py-2.5 text-sm font-medium transition-colors",
              selected
                ? "border-accent-600 text-ink-900"
                : "border-transparent text-ink-500 hover:text-ink-800",
            )}
          >
            {item.label}
            {item.badge}
          </button>
        );
      })}
    </div>
  );
}
