/**
 * Parseur CSV minimal pour `POST /shootings/{id}/engagements:import`
 * (`car_number,driver,team,client,car_model` — noms, pas d'identifiants) et sa
 * simulation en mode fixtures. Recoupe les noms avec les référentiels existants ; toute
 * ligne dont le pilote/l'écurie/le client cité est introuvable part en erreur, **jamais**
 * créée à moitié.
 */
import type { EngagementImportError } from "@/lib/api/types";
import { clients, drivers, teams } from "@/lib/api/fixtures/db";

export type ParsedEngagementLine = {
  car_number: string;
  driver: string;
  team: string;
  client: string;
  car_model: string;
};

export type ParsedRow = {
  lineNumber: number;
  line: ParsedEngagementLine;
  driverId: number | null;
  teamId: number | null;
  clientId: number | null;
};

const EXPECTED_HEADER = ["car_number", "driver", "team", "client", "car_model"];

function splitCsvLine(line: string): string[] {
  const cells: string[] = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === "," && !inQuotes) {
      cells.push(current.trim());
      current = "";
    } else {
      current += char;
    }
  }
  cells.push(current.trim());
  return cells;
}

function findByName<T extends { id: number }>(
  list: T[],
  name: string,
  getName: (item: T) => string,
): T | undefined {
  const target = name.trim().toLowerCase();
  return list.find((item) => getName(item).trim().toLowerCase() === target);
}

export function parseEngagementsCsv(csvText: string): {
  rows: ParsedRow[];
  errors: EngagementImportError[];
} {
  const lines = csvText.split(/\r?\n/).filter((l) => l.trim().length > 0);
  const rows: ParsedRow[] = [];
  const errors: EngagementImportError[] = [];

  if (lines.length === 0) {
    errors.push({ line: 0, message: "Fichier CSV vide." });
    return { rows, errors };
  }

  const header = splitCsvLine(lines[0]).map((h) => h.toLowerCase());
  const startIndex = header.join(",") === EXPECTED_HEADER.join(",") ? 1 : 0;

  for (let i = startIndex; i < lines.length; i += 1) {
    const lineNumber = i + 1;
    const cells = splitCsvLine(lines[i]);
    if (cells.length < 5) {
      errors.push({
        line: lineNumber,
        message: `Colonnes manquantes (attendu : ${EXPECTED_HEADER.join(", ")}).`,
      });
      continue;
    }
    const [car_number, driver, team, client, car_model] = cells;
    if (!car_number) {
      errors.push({ line: lineNumber, message: "Numéro de voiture manquant." });
      continue;
    }

    const driverMatch = driver ? findByName(drivers, driver, (d) => d.full_name) : undefined;
    if (driver && !driverMatch) {
      errors.push({ line: lineNumber, message: `Pilote « ${driver} » introuvable dans le référentiel.` });
      continue;
    }
    const teamMatch = team ? findByName(teams, team, (t) => t.name) : undefined;
    if (team && !teamMatch) {
      errors.push({ line: lineNumber, message: `Écurie « ${team} » introuvable dans le référentiel.` });
      continue;
    }
    const clientMatch = client ? findByName(clients, client, (c) => c.name) : undefined;
    if (client && !clientMatch) {
      errors.push({ line: lineNumber, message: `Client « ${client} » introuvable dans le référentiel.` });
      continue;
    }

    rows.push({
      lineNumber,
      line: { car_number, driver, team, client, car_model },
      driverId: driverMatch?.id ?? null,
      teamId: teamMatch?.id ?? null,
      clientId: clientMatch?.id ?? null,
    });
  }

  return { rows, errors };
}
