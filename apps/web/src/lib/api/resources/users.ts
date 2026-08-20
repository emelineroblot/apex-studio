import { API_MODE } from "@/lib/env";
import { ApiError } from "@/lib/api/errors";
import * as fixtures from "@/lib/api/fixtures/users";
import type { UserOut } from "@/lib/api/types";

/**
 * ⚠️ Contrat incomplet : aucune route `GET /users` n'existe dans `openapi.json` (66
 * routes recensées). En mode "fixtures" on retourne un jeu local pour peupler le
 * sélecteur d'équipe (`shootings/[id]`). En mode "live" cette fonction échoue
 * explicitement plutôt que d'inventer un appel — à combler côté backend avant de brancher
 * l'écran d'affectation en conditions réelles (signalé dans `implementation.md`).
 */
export async function listStaff(): Promise<UserOut[]> {
  if (API_MODE === "fixtures") return fixtures.listStaff();
  throw new ApiError(501, {
    code: "missing_contract",
    message:
      "Aucune route GET /users n'existe côté API : impossible de lister les employés en mode live.",
  });
}
