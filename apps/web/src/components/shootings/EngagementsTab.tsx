"use client";

import { useRef, useState } from "react";
import type {
  DriverOut,
  EngagementCreate,
  EngagementImportResult,
  EngagementOut,
  ClientOut,
  TeamOut,
} from "@/lib/api/types";
import * as shootingsApi from "@/lib/api/resources/shootings";
import * as engagementsApi from "@/lib/api/resources/engagements";
import { useAsync } from "@/hooks/useAsync";
import { friendlyErrorMessage } from "@/lib/api/errors";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { inputClassName } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";

export function EngagementsTab({
  shootingId,
  drivers,
  teams,
  clients,
  canWrite,
}: {
  shootingId: number;
  drivers: DriverOut[];
  teams: TeamOut[];
  clients: ClientOut[];
  canWrite: boolean;
}) {
  const { data: engagements, loading, error, reload } = useAsync(
    () => shootingsApi.listEngagements(shootingId),
    [shootingId],
  );
  const [importReport, setImportReport] = useState<EngagementImportResult | null>(null);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setImportError(null);
    setImportReport(null);
    try {
      const result = await shootingsApi.importEngagementsCsv(shootingId, file);
      setImportReport(result);
      reload();
    } catch (err) {
      setImportError(friendlyErrorMessage(err));
    } finally {
      setImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {canWrite ? (
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-ink-900">Import CSV</h2>
              <p className="text-xs text-ink-500">Colonnes attendues : car_number, driver, team, client, car_model.</p>
            </div>
            <div className="flex items-center gap-2">
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,text/csv"
                onChange={handleImport}
                className="text-sm"
                aria-label="Importer un fichier CSV d'engagements"
              />
              {importing ? <Spinner label="Import en cours…" /> : null}
            </div>
          </div>
          {importError ? (
            <div className="mt-3">
              <Notice tone="danger">{importError}</Notice>
            </div>
          ) : null}
          {importReport ? (
            <div className="mt-3 flex flex-col gap-2">
              <Notice tone={importReport.errors.length > 0 ? "warn" : "ok"}>
                {importReport.created} ligne(s) créée(s), {importReport.skipped} ignorée(s).
              </Notice>
              {importReport.errors.length > 0 ? (
                <div className="overflow-x-auto rounded-lg border border-warn-100">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-warn-100/40 text-warn-600">
                      <tr>
                        <th scope="col" className="px-3 py-2 font-medium">Ligne</th>
                        <th scope="col" className="px-3 py-2 font-medium">Erreur</th>
                      </tr>
                    </thead>
                    <tbody>
                      {importReport.errors.map((err, i) => (
                        <tr key={i} className="border-t border-warn-100">
                          <td className="px-3 py-2 font-mono">{err.line}</td>
                          <td className="px-3 py-2">{err.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </div>
          ) : null}
        </Card>
      ) : null}

      {loading ? <Spinner label="Chargement des engagements…" /> : null}
      {error ? <ErrorState message={friendlyErrorMessage(error)} onRetry={reload} /> : null}

      {!loading && !error && engagements ? (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-ink-100 bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
              <tr>
                <th scope="col" className="px-4 py-3 font-medium">N° voiture</th>
                <th scope="col" className="px-4 py-3 font-medium">Pilote</th>
                <th scope="col" className="px-4 py-3 font-medium">Écurie</th>
                <th scope="col" className="px-4 py-3 font-medium">Client</th>
                <th scope="col" className="px-4 py-3 font-medium">Modèle</th>
                {canWrite ? <th scope="col" className="px-4 py-3 font-medium">Actions</th> : null}
              </tr>
            </thead>
            <tbody>
              {engagements.map((eng) => (
                <EngagementRow
                  key={eng.id}
                  engagement={eng}
                  drivers={drivers}
                  teams={teams}
                  clients={clients}
                  canWrite={canWrite}
                  onChanged={reload}
                />
              ))}
              {canWrite ? (
                <NewEngagementRow
                  shootingId={shootingId}
                  drivers={drivers}
                  teams={teams}
                  clients={clients}
                  onCreated={reload}
                />
              ) : null}
            </tbody>
          </table>
          {engagements.length === 0 && !canWrite ? (
            <div className="p-4">
              <EmptyState title="Aucun engagement pour ce shooting" />
            </div>
          ) : null}
        </Card>
      ) : null}
    </div>
  );
}

function EngagementRow({
  engagement,
  drivers,
  teams,
  clients,
  canWrite,
  onChanged,
}: {
  engagement: EngagementOut;
  drivers: DriverOut[];
  teams: TeamOut[];
  clients: ClientOut[];
  canWrite: boolean;
  onChanged: () => void;
}) {
  const [removing, setRemoving] = useState(false);
  const driver = drivers.find((d) => d.id === engagement.driver_id);
  const team = teams.find((t) => t.id === engagement.team_id);
  const client = clients.find((c) => c.id === engagement.client_id);

  async function handleRemove() {
    if (!window.confirm(`Retirer l'engagement n°${engagement.car_number} ?`)) return;
    setRemoving(true);
    try {
      await engagementsApi.remove(engagement.id);
      onChanged();
    } finally {
      setRemoving(false);
    }
  }

  return (
    <tr className="border-b border-ink-50 last:border-0">
      <td className="px-4 py-2.5 font-mono font-medium text-ink-900">{engagement.car_number}</td>
      <td className="px-4 py-2.5 text-ink-700">{driver?.full_name ?? "—"}</td>
      <td className="px-4 py-2.5 text-ink-700">{team?.name ?? "—"}</td>
      <td className="px-4 py-2.5 text-ink-700">{client?.name ?? "—"}</td>
      <td className="px-4 py-2.5 text-ink-700">{engagement.car_model ?? "—"}</td>
      {canWrite ? (
        <td className="px-4 py-2.5">
          <Button variant="ghost" size="sm" loading={removing} onClick={handleRemove}>
            Retirer
          </Button>
        </td>
      ) : null}
    </tr>
  );
}

function NewEngagementRow({
  shootingId,
  drivers,
  teams,
  clients,
  onCreated,
}: {
  shootingId: number;
  drivers: DriverOut[];
  teams: TeamOut[];
  clients: ClientOut[];
  onCreated: () => void;
}) {
  const [carNumber, setCarNumber] = useState("");
  const [driverId, setDriverId] = useState("");
  const [teamId, setTeamId] = useState("");
  const [clientId, setClientId] = useState("");
  const [carModel, setCarModel] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAdd() {
    if (!carNumber.trim()) {
      setError("Le numéro de voiture est requis.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload: EngagementCreate = {
        car_number: carNumber.trim(),
        driver_id: driverId ? Number(driverId) : null,
        team_id: teamId ? Number(teamId) : null,
        client_id: clientId ? Number(clientId) : null,
        car_model: carModel.trim() || null,
      };
      await shootingsApi.createEngagement(shootingId, payload);
      setCarNumber("");
      setDriverId("");
      setTeamId("");
      setClientId("");
      setCarModel("");
      onCreated();
    } catch (err) {
      setError(friendlyErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <tr className="bg-ink-50/60">
      <td className="px-4 py-2.5">
        <input
          value={carNumber}
          onChange={(e) => setCarNumber(e.target.value)}
          placeholder="N°"
          aria-label="Numéro de voiture"
          className={inputClassName("w-20")}
        />
      </td>
      <td className="px-4 py-2.5">
        <select value={driverId} onChange={(e) => setDriverId(e.target.value)} aria-label="Pilote" className={inputClassName()}>
          <option value="">—</option>
          {drivers.map((d) => (
            <option key={d.id} value={d.id}>
              {d.full_name}
            </option>
          ))}
        </select>
      </td>
      <td className="px-4 py-2.5">
        <select value={teamId} onChange={(e) => setTeamId(e.target.value)} aria-label="Écurie" className={inputClassName()}>
          <option value="">—</option>
          {teams.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </td>
      <td className="px-4 py-2.5">
        <select value={clientId} onChange={(e) => setClientId(e.target.value)} aria-label="Client" className={inputClassName()}>
          <option value="">—</option>
          {clients.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </td>
      <td className="px-4 py-2.5">
        <input
          value={carModel}
          onChange={(e) => setCarModel(e.target.value)}
          placeholder="Modèle"
          aria-label="Modèle de voiture"
          className={inputClassName()}
        />
      </td>
      <td className="px-4 py-2.5">
        <Button size="sm" loading={submitting} onClick={handleAdd}>
          Ajouter
        </Button>
        {error ? <p className="mt-1 text-xs text-danger-600">{error}</p> : null}
      </td>
    </tr>
  );
}
