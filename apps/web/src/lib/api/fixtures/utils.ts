/** Utilitaires communs aux fixtures (mode "fixtures" — voir `lib/env.ts`). */
import { ApiError } from "@/lib/api/errors";

/** Latence simulée — assez sensible pour que les états de chargement soient visibles en démo. */
export function delay(ms = 260): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function paginate<T>(
  items: T[],
  cursor: string | null | undefined,
  limit: number,
): { items: T[]; next_cursor: string | null; total: number } {
  const offset = cursor ? Number.parseInt(cursor, 10) || 0 : 0;
  const page = items.slice(offset, offset + limit);
  const nextOffset = offset + limit;
  return {
    items: page,
    next_cursor: nextOffset < items.length ? String(nextOffset) : null,
    total: items.length,
  };
}

export function notFound(resource: string): never {
  throw new ApiError(404, {
    code: "not_found",
    message: `${resource} introuvable.`,
  });
}

let idSeq = 100000;
export function nextId(): number {
  idSeq += 1;
  return idSeq;
}

/**
 * Vignette placeholder déterministe (data URI SVG) — aucune photo réelle n'est encore
 * sourcée (brief, contrainte « photos de démonstration »). Pas de dépendance réseau.
 */
export function placeholderImage(
  label: string,
  opts: { tone?: string; sub?: string } = {},
): string {
  const tone = opts.tone ?? "#2a3244";
  const sub = opts.sub ?? "";
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="480" height="320">
    <rect width="480" height="320" fill="${tone}"/>
    <rect width="480" height="320" fill="url(#g)" opacity="0.25"/>
    <defs>
      <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#ffffff" stop-opacity="0.15"/>
        <stop offset="1" stop-color="#000000" stop-opacity="0.25"/>
      </linearGradient>
    </defs>
    <text x="24" y="170" font-family="Segoe UI, sans-serif" font-size="34" fill="#f4f5f9" font-weight="700">${escapeXml(
      label,
    )}</text>
    <text x="24" y="200" font-family="Segoe UI, sans-serif" font-size="16" fill="#ced4e0">${escapeXml(
      sub,
    )}</text>
  </svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

function escapeXml(value: string): string {
  return value.replace(/[<>&'"]/g, (c) => {
    switch (c) {
      case "<":
        return "&lt;";
      case ">":
        return "&gt;";
      case "&":
        return "&amp;";
      case "'":
        return "&apos;";
      default:
        return "&quot;";
    }
  });
}
