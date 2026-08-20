import type { EngagementOut, EngagementPatch } from "@/lib/api/types";
import { engagements, shootings } from "@/lib/api/fixtures/db";
import { delay, notFound } from "@/lib/api/fixtures/utils";

export async function update(id: number, payload: EngagementPatch): Promise<EngagementOut> {
  await delay(250);
  const found = engagements.find((e) => e.id === id);
  if (!found) notFound("Cet engagement");
  Object.assign(found, payload);
  return found;
}

export async function remove(id: number): Promise<void> {
  await delay(250);
  const index = engagements.findIndex((e) => e.id === id);
  if (index === -1) notFound("Cet engagement");
  const [removed] = engagements.splice(index, 1);
  const shooting = shootings.find((s) => s.id === removed.shooting_id);
  if (shooting) shooting.engagement_count = Math.max(0, shooting.engagement_count - 1);
}
