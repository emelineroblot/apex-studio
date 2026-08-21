"use client";

import Link from "next/link";
import * as statsApi from "@/lib/api/resources/stats";
import { useAsync } from "@/hooks/useAsync";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { formatPercent } from "@/lib/format";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Notice";
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
        <>
          {/*
           * Revue J2 🟠1 — « on ne fait pas passer un jeu généré pour du traitement réel »
           * (§3-N.1 du plan). `GET /stats/auto-attach-rate` ventile désormais le calcul par
           * origine (`data.real` / `data.simulated`, contrat confirmé § intégration live J2) :
           * le bandeau de contournement est remplacé par un rendu chiffré direct des deux
           * populations. Le lien vers la recherche filtrée reste en aide à la vérification,
           * pas en substitut du chiffre.
           */}
          <Notice tone="accent">
            <p>
              Le taux ci-dessous agrège des médias <strong>réels</strong> et des médias{" "}
              <strong>simulés</strong> (jeu de démonstration, § brief) — le détail par origine est ventilé
              plus bas. Vérifier dans la recherche :{" "}
              <Link href="/search?sim=0" className="font-medium underline hover:no-underline">
                médias réels
              </Link>{" "}
              ·{" "}
              <Link href="/search?sim=1" className="font-medium underline hover:no-underline">
                médias simulés
              </Link>
              .
            </p>
          </Notice>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card className="lg:col-span-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">
                Taux de rattachement automatique
              </p>
              <p className="mt-2 text-4xl font-semibold text-accent-700">{formatPercent(data.rate)}</p>
              <p className="mt-1 text-xs text-ink-500">
                {data.auto_time + data.auto_ocr} sur {data.total} média{data.total > 1 ? "s" : ""} ingéré
                {data.total > 1 ? "s" : ""} rattachés sans intervention humaine — réels et simulés confondus.
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

          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <OriginCard
              label="Médias réels"
              href="/search?sim=0"
              total={data.real.total}
              rate={data.real.rate}
              autoTotal={data.real.auto_time + data.real.auto_ocr}
            />
            <OriginCard
              label="Médias simulés"
              href="/search?sim=1"
              total={data.simulated.total}
              rate={data.simulated.rate}
              autoTotal={data.simulated.auto_time + data.simulated.auto_ocr}
            />
          </div>
        </>
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

/**
 * Ventilation réel/simulé (§3-N.1, revue J2 🟠1) — `AutoAttachRate.real`/`.simulated`
 * (`AutoAttachRatePopulation`, mêmes 6 champs que la forme de tête). Un total à 0 signifie
 * une population absente du catalogue (ex. `demo-photos/` vide : aucun média réel), pas une
 * erreur — `formatPercent(0)` reste honnête dans ce cas plutôt que masqué.
 */
function OriginCard({
  label,
  href,
  total,
  rate,
  autoTotal,
}: {
  label: string;
  href: string;
  total: number;
  rate: number;
  autoTotal: number;
}) {
  return (
    <Card>
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">{label}</p>
        <Link href={href} className="text-xs font-medium text-accent-700 underline hover:no-underline">
          Voir dans la recherche
        </Link>
      </div>
      {total === 0 ? (
        <p className="mt-2 text-sm text-ink-500">Aucun média dans cette population pour l&apos;instant.</p>
      ) : (
        <>
          <p className="mt-2 text-3xl font-semibold text-ink-900">{formatPercent(rate)}</p>
          <p className="mt-1 text-xs text-ink-500">
            {autoTotal} sur {total} média{total > 1 ? "s" : ""} rattaché{autoTotal > 1 ? "s" : ""} sans
            intervention humaine.
          </p>
          <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-ink-100">
            <div className="h-full bg-accent-600" style={{ width: `${Math.round(rate * 100)}%` }} />
          </div>
        </>
      )}
    </Card>
  );
}
