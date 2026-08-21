import { API_MODE } from "@/lib/env";
import { apiRequest } from "@/lib/api/http";
import * as fixtures from "@/lib/api/fixtures/settings";
import type { OcrSettingsOut, OcrSettingsUpdate, OcrSettingsUpdateResponse } from "@/lib/api/types";

export async function getOcr(): Promise<OcrSettingsOut> {
  if (API_MODE === "fixtures") return fixtures.getOcr();
  return apiRequest<OcrSettingsOut>("/settings/ocr");
}

/** `owner` uniquement (contrat) — la garde de rôle vit dans la page, comme les autres écrans
 * réservés au dirigeant (`cameras`, etc.) : le backend reste la seule porte faisant autorité. */
export async function updateOcr(payload: OcrSettingsUpdate): Promise<OcrSettingsUpdateResponse> {
  if (API_MODE === "fixtures") return fixtures.updateOcr(payload);
  return apiRequest<OcrSettingsUpdateResponse>("/settings/ocr", { method: "PUT", json: payload });
}
