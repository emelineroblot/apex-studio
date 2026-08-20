/**
 * ⚠️ Hors contrat — voir la note dans `fixtures/db.ts`. Utilisé uniquement pour peupler
 * le sélecteur d'affectation d'équipe (`app/(app)/shootings/[id]`, onglet Équipe) tant
 * qu'aucune route `GET /users` n'existe côté backend.
 */
import type { UserOut } from "@/lib/api/types";
import { users } from "@/lib/api/fixtures/db";
import { delay } from "@/lib/api/fixtures/utils";

export async function listStaff(): Promise<UserOut[]> {
  await delay(150);
  return users;
}
