import type { CircuitCreate, CircuitOut, Page } from "@/lib/api/types";
import { circuits } from "@/lib/api/fixtures/db";
import { delay, nextId, notFound, paginate } from "@/lib/api/fixtures/utils";

export async function list(cursor?: string | null, limit = 50): Promise<Page<CircuitOut>> {
  await delay();
  return paginate([...circuits].sort((a, b) => a.name.localeCompare(b.name, "fr")), cursor, limit);
}

export async function get(id: number): Promise<CircuitOut> {
  await delay(150);
  const found = circuits.find((c) => c.id === id);
  if (!found) notFound("Ce circuit");
  return found;
}

export async function create(payload: CircuitCreate): Promise<CircuitOut> {
  await delay(300);
  const created: CircuitOut = { id: nextId(), ...payload };
  circuits.push(created);
  return created;
}
