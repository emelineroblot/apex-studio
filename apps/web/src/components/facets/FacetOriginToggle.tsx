"use client";

import clsx from "clsx";

/**
 * Filtre `is_simulated` (§3-N.1 du plan, revue J2 🟠1) — mono-sélection à 3 états, pas une
 * facette à compteurs comme les autres (`GET /search` ne renvoie pas de ventilation
 * réel/simulé par valeur, seulement un paramètre de filtre). Sans ce contrôle, un jeu
 * généré à 100 % de médias simulés se présente à l'écran exactement comme un jeu réel —
 * ce que le plan qualifie explicitement de risque de crédibilité, pas seulement d'exactitude.
 */
export function FacetOriginToggle({
  value,
  onChange,
}: {
  value: boolean | null;
  onChange: (next: boolean | null) => void;
}) {
  const options: { value: boolean | null; label: string }[] = [
    { value: null, label: "Tous" },
    { value: false, label: "Réels" },
    { value: true, label: "Simulés" },
  ];

  return (
    <fieldset className="border-t border-ink-100 pt-3">
      <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">Origine</legend>
      <div role="radiogroup" aria-label="Origine des médias" className="flex gap-1 rounded-lg bg-ink-100 p-1">
        {options.map((option) => {
          const active = value === option.value;
          return (
            <button
              key={String(option.value)}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onChange(option.value)}
              className={clsx(
                "flex-1 rounded-md px-2 py-1 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-accent-600 focus-visible:outline-offset-1",
                active ? "bg-white text-ink-900 shadow-sm" : "text-ink-500 hover:text-ink-800",
              )}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
