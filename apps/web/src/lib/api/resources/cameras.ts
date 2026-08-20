import { API_MODE } from "@/lib/env";
import { apiRequest } from "@/lib/api/http";
import * as fixtures from "@/lib/api/fixtures/cameras";
import type { CameraOut, CameraPatch, CameraPatchResponse } from "@/lib/api/types";

export async function list(): Promise<CameraOut[]> {
  if (API_MODE === "fixtures") return fixtures.list();
  return apiRequest<CameraOut[]>("/cameras");
}

export async function update(id: number, payload: CameraPatch): Promise<CameraPatchResponse> {
  if (API_MODE === "fixtures") return fixtures.update(id, payload);
  return apiRequest<CameraPatchResponse>(`/cameras/${id}`, { method: "PATCH", json: payload });
}
