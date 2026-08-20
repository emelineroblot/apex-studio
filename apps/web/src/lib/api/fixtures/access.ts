/**
 * Cloisonnement §3-I côté fixtures uniquement — en mode "live" c'est le backend
 * (`apex/services/access.py`, `visible_shooting_ids`) qui applique la matrice de rôles ;
 * ce module la **rejoue côté client** pour que la démo hors-ligne se comporte pareil.
 */
import { getCurrentUser } from "@/lib/auth/session";
import { shootings } from "@/lib/api/fixtures/db";

export function visibleShootingIdsForCurrentUser(): number[] | null {
  const user = getCurrentUser();
  if (!user) return [];
  if (user.role === "owner") return null; // null = pas de restriction
  return shootings.filter((s) => s.staff.some((m) => m.user_id === user.id)).map((s) => s.id);
}
