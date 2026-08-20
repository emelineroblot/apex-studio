"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useAsync } from "@/hooks/useAsync";
import * as shootingsApi from "@/lib/api/resources/shootings";
import * as clientsApi from "@/lib/api/resources/clients";
import * as circuitsApi from "@/lib/api/resources/circuits";
import { SHOOTING_STATUS_LABELS } from "@/lib/labels";
import { formatDateTime, formatPercent } from "@/lib/format";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";
import { Modal } from "@/components/ui/Modal";
import { inputClassName } from "@/components/ui/Field";
import { ShootingForm } from "@/components/shootings/ShootingForm";

export default function ShootingsPage() {
  const { user } = useAuth();
  const canCreate = user?.role === "owner";
  const [createOpen, setCreateOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");
  const [clientFilter, setClientFilter] = useState("");

  const { data: clientsPage } = useAsync(() => clientsApi.list({ limit: 100 }), []);
  const { data: circuitsPage } = useAsync(() => circuitsApi.list({ limit: 100 }), []);
  const clientsById = useMemo(
    () => new Map((clientsPage?.items ?? []).map((c) => [c.id, c])),
    [clientsPage],
  );
  const circuitsById = useMemo(
    () => new Map((circuitsPage?.items ?? []).map((c) => [c.id, c])),
    [circuitsPage],
  );

  const { data, loading, error, reload } = useAsync(
    () =>
      shootingsApi.list({
        status: statusFilter || undefined,
        client_id: clientFilter ? Number(clientFilter) : undefined,
        limit: 100,
      }),
    [statusFilter, clientFilter],
  );

  return (
    <div>
      <PageHeader
        title="Shootings"
        description="Planification et suivi de l'ingestion par événement."
        actions={canCreate ? <Button onClick={() => setCreateOpen(true)}>Nouveau shooting</Button> : undefined}
      />

      <div className="mb-4 flex flex-wrap gap-3">
        <label className="flex items-center gap-2 text-sm text-ink-600">
          Statut
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className={inputClassName("w-auto")}
          >
            <option value="">Tous</option>
            <option value="planned">Programmé</option>
            <option value="done">Réalisé</option>
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-ink-600">
          Client
          <select
            value={clientFilter}
            onChange={(e) => setClientFilter(e.target.value)}
            className={inputClassName("w-auto")}
          >
            <option value="">Tous</option>
            {(clientsPage?.items ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading ? <Spinner label="Chargement des shootings…" /> : null}
      {error ? <ErrorState message={friendlyErrorMessage(error)} onRetry={reload} /> : null}

      {!loading && !error && data ? (
        data.items.length === 0 ? (
          <EmptyState
            title="Aucun shooting ne correspond"
            description="Modifiez les filtres ou créez un nouveau shooting."
            action={canCreate ? <Button onClick={() => setCreateOpen(true)}>Nouveau shooting</Button> : undefined}
          />
        ) : (
          <div className="grid gap-3">
            {data.items.map((s) => (
              <Link key={s.id} href={`/shootings/${s.id}`}>
                <Card className="transition-shadow hover:shadow-md">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <h2 className="text-sm font-semibold text-ink-900">{s.title}</h2>
                        <Badge tone={s.status === "done" ? "ok" : "accent"}>
                          {SHOOTING_STATUS_LABELS[s.status] ?? s.status}
                        </Badge>
                      </div>
                      <p className="mt-1 text-sm text-ink-500">
                        {circuitsById.get(s.circuit_id)?.name ?? `Circuit #${s.circuit_id}`}
                        {" · "}
                        {s.client_id ? (clientsById.get(s.client_id)?.name ?? `Client #${s.client_id}`) : "Sans client"}
                      </p>
                      <p className="mt-1 text-xs text-ink-400">
                        {formatDateTime(s.starts_at)} → {formatDateTime(s.ends_at)}
                      </p>
                    </div>
                    <div className="text-right text-xs text-ink-500">
                      <p>{s.media_count} médias</p>
                      <p>
                        {s.attached_count}/{s.media_count} rattachés (
                        {formatPercent(s.media_count ? s.attached_count / s.media_count : null)})
                      </p>
                    </div>
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        )
      ) : null}

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="Nouveau shooting">
        <ShootingForm
          clients={clientsPage?.items ?? []}
          circuits={circuitsPage?.items ?? []}
          onCancel={() => setCreateOpen(false)}
          onSubmit={async (payload) => {
            const created = await shootingsApi.create(payload);
            setCreateOpen(false);
            reload();
            window.location.assign(`/shootings/${created.id}`);
          }}
        />
      </Modal>
    </div>
  );
}
