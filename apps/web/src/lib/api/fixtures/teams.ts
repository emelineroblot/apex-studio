import type { Page, TeamCreate, TeamOut } from "@/lib/api/types";
import { teams } from "@/lib/api/fixtures/db";
import { delay, nextId, notFound, paginate } from "@/lib/api/fixtures/utils";

export async function list(cursor?: string | null, limit = 50): Promise<Page<TeamOut>> {
  await delay();
  return paginate([...teams].sort((a, b) => a.name.localeCompare(b.name, "fr")), cursor, limit);
}

export async function get(id: number): Promise<TeamOut> {
  await delay(150);
  const found = teams.find((t) => t.id === id);
  if (!found) notFound("Cette écurie");
  return found;
}

export async function create(payload: TeamCreate): Promise<TeamOut> {
  await delay(300);
  const created: TeamOut = { id: nextId(), ...payload };
  teams.push(created);
  return created;
}
