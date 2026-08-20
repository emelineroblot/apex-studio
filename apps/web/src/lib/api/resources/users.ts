import { API_MODE } from "@/lib/env";
import { apiRequest } from "@/lib/api/http";
import * as fixtures from "@/lib/api/fixtures/users";
import type { UserSummary } from "@/lib/api/types";

/**
 * `GET /users` (revue J1, constat 🟠 `resources/users.ts`) — liste les employés pour
 * l'onglet « Équipe » (`PUT /shootings/{id}/staff`), condition pour que l'affectation, donc
 * le cloisonnement photographe, soit réellement configurable depuis l'UI. Réservé au rôle
 * `owner` côté backend ; renvoie un `UserSummary` (id, full_name, role — **sans `email`**),
 * pas un `UserOut`. En mode "fixtures", jeu local (voir `fixtures/db.ts`).
 */
export async function listStaff(): Promise<UserSummary[]> {
  if (API_MODE === "fixtures") return fixtures.listStaff();
  return apiRequest<UserSummary[]>("/users");
}
