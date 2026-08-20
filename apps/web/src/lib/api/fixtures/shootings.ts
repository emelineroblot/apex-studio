import type {
  EngagementCreate,
  EngagementImportResult,
  EngagementOut,
  Page,
  ShootingCreate,
  ShootingOut,
  ShootingPatch,
  ShootingSummary,
  StaffMember,
} from "@/lib/api/types";
import { engagements, media, shootings } from "@/lib/api/fixtures/db";
import { ApiError } from "@/lib/api/errors";
import { delay, nextId, notFound, paginate } from "@/lib/api/fixtures/utils";
import { parseEngagementsCsv } from "@/lib/api/fixtures/csv";
import { visibleShootingIdsForCurrentUser } from "@/lib/api/fixtures/access";

export type ShootingListFilters = {
  client_id?: number | null;
  from?: string | null;
  to?: string | null;
  status?: string | null;
  /** Cloisonnement §3-I : appliqué par l'appelant (`resources/shootings.ts`) selon le rôle. */
  visibleIds?: number[] | null;
};

function toSummary(s: ShootingOut): ShootingSummary {
  const shootingMedia = media.filter((m) => m.shooting_id === s.id);
  return {
    id: s.id,
    client_id: s.client_id,
    circuit_id: s.circuit_id,
    title: s.title,
    starts_at: s.starts_at,
    ends_at: s.ends_at,
    status: s.status,
    media_count: shootingMedia.length,
    attached_count: shootingMedia.filter(
      (m) => m.attachment_status === "shooting_attached" || m.attachment_status === "engagement_attached",
    ).length,
  };
}

export async function list(
  filters: ShootingListFilters,
  cursor?: string | null,
  limit = 50,
): Promise<Page<ShootingSummary>> {
  await delay();
  let scoped = shootings;
  if (filters.visibleIds) {
    const allowed = new Set(filters.visibleIds);
    scoped = scoped.filter((s) => allowed.has(s.id));
  }
  if (filters.client_id != null) scoped = scoped.filter((s) => s.client_id === filters.client_id);
  if (filters.status) scoped = scoped.filter((s) => s.status === filters.status);
  if (filters.from) scoped = scoped.filter((s) => s.ends_at >= filters.from!);
  if (filters.to) scoped = scoped.filter((s) => s.starts_at <= filters.to!);
  const sorted = [...scoped].sort((a, b) => (a.starts_at < b.starts_at ? 1 : -1));
  const page = paginate(sorted, cursor, limit);
  return { ...page, items: page.items.map(toSummary) };
}

export async function get(id: number): Promise<ShootingOut> {
  await delay(150);
  const found = shootings.find((s) => s.id === id);
  if (!found) notFound("Ce shooting");
  const visible = visibleShootingIdsForCurrentUser();
  if (visible && !visible.includes(id)) {
    // §3-I : hors périmètre ⇒ 404, jamais 403, pour ne pas révéler l'existence de la ressource.
    notFound("Ce shooting");
  }
  return found;
}

export async function create(payload: ShootingCreate): Promise<ShootingOut> {
  await delay(350);
  if (new Date(payload.ends_at) <= new Date(payload.starts_at)) {
    throw new ApiError(422, {
      code: "validation_error",
      message: "La fin de la plage horaire doit être après le début.",
    });
  }
  const created: ShootingOut = {
    id: nextId(),
    client_id: payload.client_id ?? null,
    circuit_id: payload.circuit_id,
    title: payload.title,
    starts_at: payload.starts_at,
    ends_at: payload.ends_at,
    status: "planned",
    quota_bytes: payload.quota_bytes ?? 2147483648,
    notes: payload.notes ?? null,
    staff: [],
    engagement_count: 0,
  };
  shootings.push(created);
  return created;
}

export async function update(id: number, payload: ShootingPatch): Promise<ShootingOut> {
  await delay(300);
  const found = shootings.find((s) => s.id === id);
  if (!found) notFound("Ce shooting");
  Object.assign(found, payload);
  return found;
}

export async function setStaff(id: number, userIds: number[]): Promise<StaffMember[]> {
  await delay(300);
  const found = shootings.find((s) => s.id === id);
  if (!found) notFound("Ce shooting");
  found.staff = userIds.map((user_id) => ({ user_id, role: "photographer" }));
  return found.staff;
}

export async function listEngagements(shootingId: number): Promise<EngagementOut[]> {
  await delay(150);
  return engagements.filter((e) => e.shooting_id === shootingId);
}

export async function createEngagement(
  shootingId: number,
  payload: EngagementCreate,
): Promise<EngagementOut> {
  await delay(250);
  const duplicate = engagements.find(
    (e) => e.shooting_id === shootingId && e.car_number === payload.car_number,
  );
  if (duplicate) {
    throw new ApiError(409, {
      code: "duplicate_car_number",
      message: `Le numéro « ${payload.car_number} » est déjà engagé sur ce shooting.`,
    });
  }
  const created: EngagementOut = {
    id: nextId(),
    shooting_id: shootingId,
    car_number: payload.car_number,
    driver_id: payload.driver_id ?? null,
    team_id: payload.team_id ?? null,
    client_id: payload.client_id ?? null,
    car_model: payload.car_model ?? null,
  };
  engagements.push(created);
  const shooting = shootings.find((s) => s.id === shootingId);
  if (shooting) shooting.engagement_count += 1;
  return created;
}

export async function importEngagementsCsv(
  shootingId: number,
  csvText: string,
): Promise<EngagementImportResult> {
  await delay(500);
  const { rows, errors } = parseEngagementsCsv(csvText);
  let created = 0;
  let skipped = 0;

  for (const row of rows) {
    if (engagements.some((e) => e.shooting_id === shootingId && e.car_number === row.line.car_number)) {
      skipped += 1;
      errors.push({ line: row.lineNumber, message: `Numéro « ${row.line.car_number} » déjà présent, ligne ignorée.` });
      continue;
    }
    engagements.push({
      id: nextId(),
      shooting_id: shootingId,
      car_number: row.line.car_number,
      driver_id: row.driverId,
      team_id: row.teamId,
      client_id: row.clientId,
      car_model: row.line.car_model || null,
    });
    created += 1;
  }

  const shooting = shootings.find((s) => s.id === shootingId);
  if (shooting) shooting.engagement_count += created;

  return { created, skipped, errors };
}
