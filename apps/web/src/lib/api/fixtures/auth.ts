import { ApiError } from "@/lib/api/errors";
import type { DemoAccount, TokenResponse, UserOut } from "@/lib/api/types";
import { credentials, demoAccounts, users } from "@/lib/api/fixtures/db";
import { delay } from "@/lib/api/fixtures/utils";

const tokensToUsers = new Map<string, UserOut>();

export async function login(email: string, password: string): Promise<TokenResponse> {
  await delay();
  const user = users.find((u) => u.email.toLowerCase() === email.toLowerCase());
  const expectedPassword = credentials.get(email);
  if (!user || !expectedPassword || expectedPassword !== password) {
    throw new ApiError(401, {
      code: "invalid_credentials",
      message: "E-mail ou mot de passe incorrect.",
    });
  }
  const token = `fixture-token-${user.id}-${Date.now()}`;
  tokensToUsers.set(token, user);
  return { access_token: token, token_type: "bearer", expires_in: 28800, user };
}

export async function me(token: string | null): Promise<UserOut> {
  await delay(120);
  const user = token ? tokensToUsers.get(token) : undefined;
  if (!user) {
    throw new ApiError(401, { code: "unauthorized", message: "Session expirée, reconnectez-vous." });
  }
  return user;
}

export async function listDemoAccounts(): Promise<DemoAccount[]> {
  await delay(150);
  return demoAccounts;
}
