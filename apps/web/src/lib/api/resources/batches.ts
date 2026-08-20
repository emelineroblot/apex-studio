import { API_MODE } from "@/lib/env";
import { apiRequest } from "@/lib/api/http";
import * as fixtures from "@/lib/api/fixtures/batches";
import type { BatchCloseResponse, BatchCreateResponse, BatchStatusResponse, FileUploadResponse } from "@/lib/api/types";

export async function create(payload: {
  expected_count: number;
  shooting_hint_id?: number | null;
}): Promise<BatchCreateResponse> {
  if (API_MODE === "fixtures") return fixtures.create(payload);
  return apiRequest<BatchCreateResponse>("/batches", { method: "POST", json: payload });
}

export async function uploadFile(
  batchId: number,
  file: File,
  idempotencyKey: string,
): Promise<FileUploadResponse> {
  if (API_MODE === "fixtures") return fixtures.uploadFile(batchId, file, idempotencyKey);
  const form = new FormData();
  form.append("file", file);
  return apiRequest<FileUploadResponse>(`/batches/${batchId}/files`, {
    method: "POST",
    body: form,
    headers: { "Idempotency-Key": idempotencyKey },
  });
}

export async function close(batchId: number): Promise<BatchCloseResponse> {
  if (API_MODE === "fixtures") return fixtures.close(batchId);
  return apiRequest<BatchCloseResponse>(`/batches/${batchId}/close`, { method: "POST" });
}

export async function getStatus(batchId: number): Promise<BatchStatusResponse> {
  if (API_MODE === "fixtures") return fixtures.getStatus(batchId);
  return apiRequest<BatchStatusResponse>(`/batches/${batchId}`);
}
