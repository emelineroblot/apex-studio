import type { DriverCreate, DriverOut, Page } from "@/lib/api/types";
import { drivers } from "@/lib/api/fixtures/db";
import { delay, nextId, notFound, paginate } from "@/lib/api/fixtures/utils";

export async function list(cursor?: string | null, limit = 50): Promise<Page<DriverOut>> {
  await delay();
  return paginate(
    [...drivers].sort((a, b) => a.full_name.localeCompare(b.full_name, "fr")),
    cursor,
    limit,
  );
}

export async function get(id: number): Promise<DriverOut> {
  await delay(150);
  const found = drivers.find((d) => d.id === id);
  if (!found) notFound("Ce pilote");
  return found;
}

export async function create(payload: DriverCreate): Promise<DriverOut> {
  await delay(300);
  const created: DriverOut = { id: nextId(), ...payload };
  drivers.push(created);
  return created;
}
