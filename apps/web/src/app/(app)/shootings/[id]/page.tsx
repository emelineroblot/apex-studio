"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useAsync } from "@/hooks/useAsync";
import * as shootingsApi from "@/lib/api/resources/shootings";
import * as clientsApi from "@/lib/api/resources/clients";
import * as circuitsApi from "@/lib/api/resources/circuits";
import * as driversApi from "@/lib/api/resources/drivers";
import * as teamsApi from "@/lib/api/resources/teams";
import { SHOOTING_STATUS_LABELS } from "@/lib/labels";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { PageHeader } from "@/components/ui/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { ErrorState, Spinner } from "@/components/ui/States";
import { Tabs } from "@/components/ui/Tabs";
import { InfosTab } from "@/components/shootings/InfosTab";
import { EngagementsTab } from "@/components/shootings/EngagementsTab";
import { StaffTab } from "@/components/shootings/StaffTab";
import { MediaTab } from "@/components/shootings/MediaTab";

const TAB_ITEMS = [
  { id: "infos", label: "Infos" },
  { id: "engagements", label: "Engagements" },
  { id: "staff", label: "Équipe" },
  { id: "media", label: "Médias" },
];

export default function ShootingDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const shootingId = Number(id);
  const { user } = useAuth();
  const canWrite = user?.role === "owner";
  const [tab, setTab] = useState("infos");

  const { data: shooting, loading, error, reload } = useAsync(
    () => shootingsApi.get(shootingId),
    [shootingId],
  );
  const { data: clientsPage } = useAsync(() => clientsApi.list({ limit: 100 }), []);
  const { data: circuitsPage } = useAsync(() => circuitsApi.list({ limit: 100 }), []);
  const { data: driversPage } = useAsync(() => driversApi.list({ limit: 100 }), []);
  const { data: teamsPage } = useAsync(() => teamsApi.list({ limit: 100 }), []);

  return (
    <div>
      <Link href="/shootings" className="text-sm text-ink-500 hover:text-accent-600">
        ← Retour aux shootings
      </Link>

      {loading ? <Spinner label="Chargement du shooting…" /> : null}
      {error ? <ErrorState message={friendlyErrorMessage(error)} onRetry={reload} /> : null}

      {shooting ? (
        <>
          <PageHeader
            title={shooting.title}
            description={`${shooting.engagement_count} engagement(s)`}
            actions={<Badge tone={shooting.status === "done" ? "ok" : "accent"}>{SHOOTING_STATUS_LABELS[shooting.status]}</Badge>}
          />

          <Tabs items={TAB_ITEMS} active={tab} onChange={setTab} label="Sections du shooting" />

          <div className="mt-5" role="tabpanel">
            {tab === "infos" ? (
              <InfosTab
                shooting={shooting}
                clients={clientsPage?.items ?? []}
                circuits={circuitsPage?.items ?? []}
                canWrite={canWrite}
                onUpdated={reload}
              />
            ) : null}
            {tab === "engagements" ? (
              <EngagementsTab
                shootingId={shooting.id}
                drivers={driversPage?.items ?? []}
                teams={teamsPage?.items ?? []}
                clients={clientsPage?.items ?? []}
                canWrite
              />
            ) : null}
            {tab === "staff" ? <StaffTab shooting={shooting} canWrite={canWrite} onUpdated={reload} /> : null}
            {tab === "media" ? <MediaTab shootingId={shooting.id} /> : null}
          </div>
        </>
      ) : null}
    </div>
  );
}
