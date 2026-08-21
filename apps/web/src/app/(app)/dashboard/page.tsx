"use client";

import * as statsApi from "@/lib/api/resources/stats";
import { useAsync } from "@/hooks/useAsync";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { formatPercent } from "@/lib/format";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { ErrorState, Spinner } from "@/components/ui/States";

/**
 * Première version du tableau de bord (§ tâche 5 du brief — « l'indicateur produit du
 * jalon, il doit être visible, pas enterré »). Les 3 autres indicateurs (chiffre
 * d'affaires, shootings, volume ingéré) rejoignent cet écran au jalon J3
 * (`DashboardOut`, § contrat J3 du plan) — ce n'est pas un oubli, juste hors périmètre J2.
 */
export default function DashboardPage() {
  const { data, loading, error, reload } = useAsync(() => statsApi.autoAttachRate({}), []);

  return (
    <div>
      <PageHeader title="Tableau de bord" description="Indicateur du jalon : rattachement automatique." />

      {loading ? <Spinner label="Calcul du taux de rattachement…" /> : null}
      {error ? <ErrorState message={friendlyErrorMessage(error)} onRetry={reload} /> : null}

      {!loading && !error && data ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card className="lg:col-span-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">
              Taux de rattachement automatique
            </p>
            <p className="mt-2 text-4xl font-semibold text-accent-700">{formatPercent(data.rate)}</p>
            <p className="mt-1 text-xs text-ink-500">
              {data.auto_time + data.auto_ocr} sur {data.total} média{data.total > 1 ? "s" : ""} ingéré
              {data.total > 1 ? "s" : ""} rattachés sans intervention humaine.
            </p>
            <div className="mt-4 h-3 w-full overflow-hidden rounded-full bg-ink-100">
              <div className="h-full bg-accent-600" style={{ width: `${Math.round(data.rate * 100)}%` }} />
            </div>
          </Card>

          <Breakdown label="Fenêtre temporelle" value={data.auto_time} total={data.total} tone="bg-accent-500" />
          <Breakdown label="Lecture OCR" value={data.auto_ocr} total={data.total} tone="bg-ok-500" />
          <Breakdown label="Rattachement manuel" value={data.human} total={data.total} tone="bg-warn-500" />
          <Breakdown label="Toujours à rattacher" value={data.unattached} total={data.total} tone="bg-ink-300" />
        </div>
      ) : null}
    </div>
  );
}

function Breakdown({ label, value, total, tone }: { label: string; value: number; total: number; tone: string }) {
  const ratio = total > 0 ? value / total : 0;
  return (
    <Card>
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-ink-900">{value}</p>
      <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-ink-100">
        <div className={`h-full ${tone}`} style={{ width: `${Math.round(ratio * 100)}%` }} />
      </div>
      <p className="mt-1 text-xs text-ink-400">{formatPercent(ratio)}</p>
    </Card>
  );
}
