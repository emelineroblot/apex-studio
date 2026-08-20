"use client";

import { useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useAsync } from "@/hooks/useAsync";
import * as clientsApi from "@/lib/api/resources/clients";
import type { ClientCreate } from "@/lib/api/types";
import { CLIENT_KIND_LABELS } from "@/lib/labels";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";
import { Modal } from "@/components/ui/Modal";
import { ClientForm } from "@/components/clients/ClientForm";

export default function ClientsPage() {
  const { user } = useAuth();
  const canWrite = user?.role === "owner";
  const [createOpen, setCreateOpen] = useState(false);
  const { data, loading, error, reload } = useAsync(() => clientsApi.list({ limit: 100 }), []);

  return (
    <div>
      <PageHeader
        title="Clients"
        description="Écuries, pilotes indépendants et sponsors du studio."
        actions={
          canWrite ? (
            <Button onClick={() => setCreateOpen(true)}>Nouveau client</Button>
          ) : undefined
        }
      />

      {loading ? <Spinner label="Chargement des clients…" /> : null}
      {error ? <ErrorState message={friendlyErrorMessage(error)} onRetry={reload} /> : null}

      {!loading && !error && data ? (
        data.items.length === 0 ? (
          <EmptyState
            title="Aucun client enregistré"
            description="Ajoutez le premier client pour pouvoir lui rattacher des shootings."
            action={canWrite ? <Button onClick={() => setCreateOpen(true)}>Nouveau client</Button> : undefined}
          />
        ) : (
          <Card className="overflow-x-auto p-0">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-ink-100 bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
                <tr>
                  <th scope="col" className="px-4 py-3 font-medium">Nom</th>
                  <th scope="col" className="px-4 py-3 font-medium">Type</th>
                  <th scope="col" className="px-4 py-3 font-medium">Contact</th>
                  <th scope="col" className="px-4 py-3 font-medium">Téléphone</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((client) => (
                  <tr key={client.id} className="border-b border-ink-50 last:border-0 hover:bg-ink-50">
                    <td className="px-4 py-3">
                      <Link
                        href={`/clients/${client.id}`}
                        className="font-medium text-ink-900 hover:text-accent-600 focus-visible:outline-2 focus-visible:outline-accent-600"
                      >
                        {client.name}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-ink-600">{CLIENT_KIND_LABELS[client.kind] ?? client.kind}</td>
                    <td className="px-4 py-3 text-ink-600">{client.contact_email ?? client.contact_name ?? "—"}</td>
                    <td className="px-4 py-3 text-ink-600">{client.phone ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )
      ) : null}

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="Nouveau client">
        <ClientForm
          onCancel={() => setCreateOpen(false)}
          onSubmit={async (payload: ClientCreate) => {
            await clientsApi.create(payload);
            setCreateOpen(false);
            reload();
          }}
        />
      </Modal>
    </div>
  );
}
