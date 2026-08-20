"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useAsync } from "@/hooks/useAsync";
import * as clientsApi from "@/lib/api/resources/clients";
import { CLIENT_KIND_LABELS } from "@/lib/labels";
import { formatDateTime } from "@/lib/format";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorState, Spinner } from "@/components/ui/States";
import { Modal } from "@/components/ui/Modal";
import { ClientForm } from "@/components/clients/ClientForm";

export default function ClientDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const clientId = Number(id);
  const { user } = useAuth();
  const canWrite = user?.role === "owner";
  const [editOpen, setEditOpen] = useState(false);
  const { data: client, loading, error, reload } = useAsync(() => clientsApi.get(clientId), [clientId]);

  return (
    <div>
      <Link href="/clients" className="text-sm text-ink-500 hover:text-accent-600">
        ← Retour aux clients
      </Link>

      {loading ? <Spinner label="Chargement du client…" /> : null}
      {error ? <ErrorState message={friendlyErrorMessage(error)} onRetry={reload} /> : null}

      {client ? (
        <>
          <PageHeader
            title={client.name}
            description={CLIENT_KIND_LABELS[client.kind] ?? client.kind}
            actions={canWrite ? <Button variant="secondary" onClick={() => setEditOpen(true)}>Modifier</Button> : undefined}
          />

          <div className="grid gap-4 sm:grid-cols-2">
            <Card>
              <h2 className="mb-3 text-sm font-semibold text-ink-900">Contact</h2>
              <dl className="flex flex-col gap-2 text-sm text-ink-700">
                <div className="flex justify-between gap-4">
                  <dt className="text-ink-500">Contact</dt>
                  <dd>{client.contact_name ?? "—"}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-ink-500">E-mail</dt>
                  <dd>{client.contact_email ?? "—"}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-ink-500">Téléphone</dt>
                  <dd>{client.phone ?? "—"}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-ink-500">Adresse</dt>
                  <dd className="text-right">{client.address ?? "—"}</dd>
                </div>
              </dl>
            </Card>
            <Card>
              <h2 className="mb-3 text-sm font-semibold text-ink-900">Notes</h2>
              <p className="text-sm text-ink-700">{client.notes ?? "Aucune note."}</p>
              <p className="mt-4 text-xs text-ink-400">
                Créé le {formatDateTime(client.created_at)} · modifié le {formatDateTime(client.updated_at)}
              </p>
            </Card>
          </div>

          <Card className="mt-4">
            <h2 className="mb-2 text-sm font-semibold text-ink-900">Historique des shootings</h2>
            <p className="text-sm text-ink-500">
              Rien à afficher pour ce jalon — la facturation et le chiffre d&apos;affaires arrivent au
              jalon J3.
            </p>
          </Card>

          <Modal open={editOpen} onClose={() => setEditOpen(false)} title="Modifier le client">
            <ClientForm
              initial={client}
              onCancel={() => setEditOpen(false)}
              onSubmit={async (payload) => {
                await clientsApi.update(clientId, payload);
                setEditOpen(false);
                reload();
              }}
            />
          </Modal>
        </>
      ) : null}
    </div>
  );
}
