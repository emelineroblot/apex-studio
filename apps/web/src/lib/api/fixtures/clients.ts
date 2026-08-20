import type { ClientCreate, ClientOut, ClientUpdate, Page } from "@/lib/api/types";
import { clients } from "@/lib/api/fixtures/db";
import { delay, nextId, notFound, paginate } from "@/lib/api/fixtures/utils";

export async function list(cursor?: string | null, limit = 50): Promise<Page<ClientOut>> {
  await delay();
  return paginate(
    [...clients].sort((a, b) => a.name.localeCompare(b.name, "fr")),
    cursor,
    limit,
  );
}

export async function get(id: number): Promise<ClientOut> {
  await delay(150);
  const found = clients.find((c) => c.id === id);
  if (!found) notFound("Ce client");
  return found;
}

export async function create(payload: ClientCreate): Promise<ClientOut> {
  await delay(300);
  const now = new Date().toISOString();
  const created: ClientOut = { id: nextId(), created_at: now, updated_at: now, ...payload };
  clients.push(created);
  return created;
}

export async function update(id: number, payload: ClientUpdate): Promise<ClientOut> {
  await delay(300);
  const found = clients.find((c) => c.id === id);
  if (!found) notFound("Ce client");
  Object.assign(found, payload, { updated_at: new Date().toISOString() });
  return found;
}

export async function remove(id: number): Promise<void> {
  await delay(250);
  const index = clients.findIndex((c) => c.id === id);
  if (index === -1) notFound("Ce client");
  clients.splice(index, 1);
}
