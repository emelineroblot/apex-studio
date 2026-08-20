/** Variables d'environnement publiques — un seul point de lecture, jamais `process.env` ailleurs. */

export const API_BASE_URL: string =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export const API_PREFIX = "/api/v1";

export type ApiMode = "fixtures" | "live";

export const API_MODE: ApiMode =
  process.env.NEXT_PUBLIC_API_MODE === "live" ? "live" : "fixtures";
