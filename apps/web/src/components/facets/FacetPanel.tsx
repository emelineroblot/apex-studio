"use client";

import type { Facets } from "@/lib/api/types";
import type { SearchFilterState } from "@/lib/search/urlState";
import { FacetCheckboxGroup } from "@/components/facets/FacetCheckboxGroup";
import { FacetCheckboxGroupText } from "@/components/facets/FacetCheckboxGroupText";
import { FacetBucketList } from "@/components/facets/FacetBucketList";
import { FacetStatusGroup } from "@/components/facets/FacetStatusGroup";
import { FacetOriginToggle } from "@/components/facets/FacetOriginToggle";
import { inputClassName } from "@/components/ui/Field";

/**
 * Panneau de facettes latéral (§ tâche 3) — toutes les facettes du brief : client, shooting,
 * circuit, date, pilote, écurie, numéro de voiture, boîtier, objectif, plages ISO/focale,
 * statut. Chacune affiche son compteur (`Facets`, calculé « sauf soi » pour les
 * multi-sélections — § `lib/search/engine.ts`).
 */
export function FacetPanel({
  facets,
  filters,
  onChange,
}: {
  facets: Facets;
  filters: SearchFilterState;
  onChange: (patch: Partial<SearchFilterState>) => void;
}) {
  return (
    <div className="flex flex-col gap-4 rounded-xl border border-ink-100 bg-white p-4">
      <div>
        <label htmlFor="search-fulltext" className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-ink-500">
          Légendes et mots-clés
        </label>
        <input
          id="search-fulltext"
          type="search"
          value={filters.q}
          onChange={(e) => onChange({ q: e.target.value })}
          placeholder="ex. « virage 3 » pluie"
          className={inputClassName()}
        />
      </div>

      <fieldset className="border-t border-ink-100 pt-3">
        <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">Date</legend>
        <div className="flex items-center gap-2">
          <input
            type="date"
            aria-label="Du"
            value={filters.date_from}
            onChange={(e) => onChange({ date_from: e.target.value })}
            className={inputClassName("text-xs")}
          />
          <span className="text-ink-400">→</span>
          <input
            type="date"
            aria-label="Au"
            value={filters.date_to}
            onChange={(e) => onChange({ date_to: e.target.value })}
            className={inputClassName("text-xs")}
          />
        </div>
      </fieldset>

      <FacetCheckboxGroup
        legend="Shooting"
        terms={facets.shooting}
        selected={filters.shooting_id}
        onChange={(v) => onChange({ shooting_id: v })}
      />
      <FacetCheckboxGroup
        legend="Client"
        terms={facets.client}
        selected={filters.client_id}
        onChange={(v) => onChange({ client_id: v })}
      />
      <FacetCheckboxGroup
        legend="Circuit"
        terms={facets.circuit}
        selected={filters.circuit_id}
        onChange={(v) => onChange({ circuit_id: v })}
      />
      <FacetCheckboxGroup
        legend="Pilote"
        terms={facets.driver}
        selected={filters.driver_id}
        onChange={(v) => onChange({ driver_id: v })}
      />
      <FacetCheckboxGroup
        legend="Écurie"
        terms={facets.team}
        selected={filters.team_id}
        onChange={(v) => onChange({ team_id: v })}
      />
      <FacetCheckboxGroupText
        legend="Numéro de voiture"
        terms={facets.car_number}
        selected={filters.car_number}
        onChange={(v) => onChange({ car_number: v })}
      />
      <FacetCheckboxGroup
        legend="Boîtier"
        terms={facets.camera}
        selected={filters.camera_id}
        onChange={(v) => onChange({ camera_id: v })}
      />
      <FacetCheckboxGroupText
        legend="Objectif"
        terms={facets.lens}
        selected={filters.lens}
        onChange={(v) => onChange({ lens: v })}
      />
      <FacetBucketList
        legend="ISO"
        buckets={facets.iso}
        unit="ISO"
        activeMin={filters.iso_min}
        activeMax={filters.iso_max}
        onChange={({ min, max }) => onChange({ iso_min: min, iso_max: max })}
      />
      <FacetBucketList
        legend="Focale"
        buckets={facets.focal}
        unit="mm"
        activeMin={filters.focal_min}
        activeMax={filters.focal_max}
        onChange={({ min, max }) => onChange({ focal_min: min, focal_max: max })}
      />
      <FacetStatusGroup terms={facets.status} selected={filters.status} onChange={(v) => onChange({ status: v })} />
      <FacetOriginToggle value={filters.is_simulated} onChange={(v) => onChange({ is_simulated: v })} />
    </div>
  );
}
