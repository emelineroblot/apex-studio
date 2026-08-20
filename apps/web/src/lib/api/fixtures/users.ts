/**
 * Rejoue `GET /users` en mode "fixtures" — peuple le sélecteur d'affectation d'équipe
 * (`app/(app)/shootings/[id]`, onglet Équipe). Voir `fixtures/db.ts`.
 */
import type { UserSummary } from "@/lib/api/types";
import { users } from "@/lib/api/fixtures/db";
import { delay } from "@/lib/api/fixtures/utils";

/** `users` (fixtures, avec `email`) est structurellement assignable à `UserSummary`
 * (id, full_name, role) : le champ `email` supplémentaire n'est pas exposé au composant
 * appelant, qui type son résultat en `UserSummary[]` comme en mode "live". */
export async function listStaff(): Promise<UserSummary[]> {
  await delay(150);
  return users;
}
