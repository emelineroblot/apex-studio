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
           * (§3-N.1 du plan). `GET /stats/auto-attach-rate` agrège encore réel et simulé
           * sans ventilation (le backend doit l'ajouter au contrat, § `implementation.md`,
           * point resté ouvert plutôt que deviné) : en attendant cette évolution du contrat,
           * ce bandeau rend la présence de médias simulés dans ce chiffre explicite et
           * renvoie vers la recherche — qui, elle, filtre déjà `is_simulated` — pour que
           * quiconque veuille le taux « réel seul » puisse le vérifier en un clic plutôt que
           * de découvrir après coup que la démonstration mélangeait les deux.
           */}
          <Notice tone="accent">
            <p>
              Ce taux agrège des médias <strong>réels</strong> et des médias <strong>simulés</strong> (jeu de
              démonstration, § brief). Consultez le détail par origine dans la recherche :{" "}
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
