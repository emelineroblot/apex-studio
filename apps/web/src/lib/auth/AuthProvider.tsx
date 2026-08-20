"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { UserOut } from "@/lib/api/types";
import { login as loginRequest } from "@/lib/api/resources/auth";
import {
  clearSession,
  getSession,
  setSession as persistSession,
  subscribeSession,
} from "@/lib/auth/session";

type AuthContextValue = {
  /** `undefined` tant que la session n'a pas été lue côté client (évite le flash SSR). */
  user: UserOut | null | undefined;
  login: (email: string, password: string) => Promise<UserOut>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserOut | null | undefined>(undefined);

  useEffect(() => {
    setUser(getSession()?.user ?? null);
    return subscribeSession((session) => setUser(session?.user ?? null));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const result = await loginRequest({ email, password });
    persistSession({ token: result.access_token, user: result.user });
    return result.user;
  }, []);

  const logout = useCallback(() => {
    clearSession();
  }, []);

  const value = useMemo(() => ({ user, login, logout }), [user, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth() doit être utilisé sous <AuthProvider>.");
  return ctx;
}
