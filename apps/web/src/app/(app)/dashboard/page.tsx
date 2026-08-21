"use client";

import Link from "next/link";
import * as billingApi from "@/lib/api/resources/billing";
import { useAsync } from "@/hooks/useAsync";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { formatPercent } from "@/lib/format";
import { formatEuros } from "@/lib/billing";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { ErrorState, Spinner } from "@/components/ui/States";

/**
 * Tableau de bord — version J3.
 *
 * **Aucun calcul ici.** Les quatre indicateurs sont lus tels quels depuis `GET /dashboard`
 * (§ contrat J3). Un chiffre recalculé côté interface finit par diverger de celui du
 * backend le jour où une règle change d'un seul côté, et c'est devant un client qu'on s'en
 * aperçoit. La seule opération faite ici est un formatage.
 *
 * Le volume ingéré distingue **réel** et **simulé** : le jeu de démonstration porte
 * l'écrasante majorité du volume, et un tableau de bord qui n'afficherait que l'agrégat
 * donnerait l'illusion d'un traitement réel à grande échelle (revue J2, 🟠 n°1).
 */
export default function DashboardPage() {
  const { data, loading, error, reload } = useAsync(() => billingApi.dashboard({}), []);

  return (
    <div>
      <PageHeader
        title="Tableau de bord"
        description="Chiffre d'affaires, activité et qualité du rattachement automatique."
      />

      {loading ? <Spinner label="Chargement des indicateurs…" /> : null}
      {error ? <ErrorState message={friendlyErrorMessage(error)} onRetry={reload} /> : null}

      {!loading && !error && data ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card>
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">
                Chiffre d&apos;affaires facturé
              </p>
              <p className="mt-2 text-3xl font-semibold text-ink-900">
                {formatEuros(data.revenue_cents)}
              </p>
              <p className="mt-1 text-xs text-ink-500">Factures émises uniquement.</p>
            </Card>

            <Card>
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">
                Shootings réalisés
              </p>
              <p className="mt-2 text-3xl font-semibold text-ink-900">{data.shootings_done}</p>
              <p className="mt-1 text-xs text-ink-500">
                {data.shootings_upcoming} à venir
              </p>
            </Card>

            <Card>
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">
                Photos ingérées
              </p>
              <p className="mt-2 text-3xl font-semibold text-ink-900">
                {data.media_ingested.total.toLocaleString("fr-FR")}
              </p>
              <p className="mt-1 text-xs text-ink-500">
                dont <strong className="text-ink-700">{data.media_ingested.real.toLocaleString("fr-FR")}</strong>{" "}
                réelles et {data.media_ingested.simulated.toLocaleString("fr-FR")} simulées
              </p>
            </Card>

            <Card>
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">
                Rattachement automatique
              </p>
              <p className="mt-2 text-3xl font-semibold text-accent-700">
                {formatPercent(data.auto_attach_rate)}
              </p>
              <p className="mt-1 text-xs text-ink-500">
                Sans intervention humaine, doublons exclus.
              </p>
            </Card>
          </div>

          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <Card>
              <p className="text-sm font-medium text-ink-900">Ce que dit le taux</p>
              <p className="mt-2 text-sm leading-relaxed text-ink-600">
                Une photo compte comme rattachée automatiquement quand ni le studio ni
                personne n&apos;a eu à trancher : l&apos;horodatage a suffi, ou la lecture du
                numéro a été assez sûre. Les cas arbitrés à la main sont exclus, c&apos;est ce
                qui rend l&apos;indicateur honnête.
              </p>
              <Link
                href="/review"
                className="mt-3 inline-block text-sm font-medium text-accent-700 underline hover:no-underline"
              >
                Voir la file de validation
              </Link>
            </Card>
            <Card>
              <p className="text-sm font-medium text-ink-900">Suite du travail</p>
              <ul className="mt-2 space-y-1 text-sm text-ink-600">
                <li>
                  <Link href="/quotes" className="text-accent-700 underline hover:no-underline">
                    Devis
                  </Link>{" "}
                  — accepter crée le shooting.
                </li>
                <li>
                  <Link href="/collections" className="text-accent-700 underline hover:no-underline">
                    Collections
                  </Link>{" "}
                  — partager une sélection à un client.
                </li>
                <li>
                  <Link href="/invoices" className="text-accent-700 underline hover:no-underline">
                    Factures
                  </Link>{" "}
                  — issues des sélections validées.
                </li>
              </ul>
            </Card>
          </div>
        </>
      ) : null}
    </div>
  );
}
