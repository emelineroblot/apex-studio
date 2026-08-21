import { beforeEach, describe, expect, it } from "vitest";
import {
  clearClientSession,
  getClientSession,
  isExpired,
  setClientSession,
  type ClientSession,
} from "@/lib/client/session";
import { getToken, setSession } from "@/lib/auth/session";
import type { PublicCollectionRef } from "@/lib/api/types";

const COLLECTION: PublicCollectionRef = {
  title: "GP de Nogaro",
  description: null,
  item_count: 3,
  studio_name: "Studio Chicane",
};

function session(expiresInMs: number): ClientSession {
  return {
    accessToken: "jeton-client",
    expiresAt: Date.now() + expiresInMs,
    collection: COLLECTION,
  };
}

describe("session client — cloisonnée du back-office", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("ne partage rien avec la session studio", () => {
    // Une session studio ouverte dans le même navigateur ne doit ni fournir, ni recevoir
    // le jeton client : c'est le pendant navigateur du routeur `/public` cloisonné.
    setSession({
      token: "jeton-studio",
      user: {
        id: 1,
        email: "owner@apex.test",
        role: "owner",
        full_name: "Propriétaire",
      },
    });
    setClientSession("lien-abc", session(60_000));

    expect(getToken()).toBe("jeton-studio");
    expect(getClientSession("lien-abc")?.accessToken).toBe("jeton-client");
    expect(getToken()).not.toBe(getClientSession("lien-abc")?.accessToken);
  });

  it("isole deux liens ouverts en parallèle", () => {
    // Deux collections dans deux onglets : fermer l'une ne doit pas déconnecter l'autre.
    setClientSession("lien-abc", { ...session(60_000), accessToken: "jeton-A" });
    setClientSession("lien-xyz", { ...session(60_000), accessToken: "jeton-B" });

    clearClientSession("lien-abc");

    expect(getClientSession("lien-abc")).toBeNull();
    expect(getClientSession("lien-xyz")?.accessToken).toBe("jeton-B");
  });

  it("considère une session comme expirée avant son échéance réelle", () => {
    // La marge évite qu'une requête partie juste avant l'échéance échoue en vol.
    expect(isExpired(session(10_000))).toBe(true);
    expect(isExpired(session(120_000))).toBe(false);
  });
});
