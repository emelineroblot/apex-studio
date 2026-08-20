import { API_MODE } from "@/lib/env";
import { apiRequest } from "@/lib/api/http";
import * as fixtures from "@/lib/api/fixtures/auth";
import type { DemoAccount, TokenResponse } from "@/lib/api/types";

export async function login(payload: { email: string; password: string }): Promise<TokenResponse> {
  if (API_MODE === "fixtures") return fixtures.login(payload.email, payload.password);
  return apiRequest<TokenResponse>("/auth/login", { method: "POST", json: payload, skipAuth: true });
}

export async function demoAccounts(): Promise<DemoAccount[]> {
  if (API_MODE === "fixtures") return fixtures.listDemoAccounts();
  return apiRequest<DemoAccount[]>("/demo/accounts", { skipAuth: true });
}
