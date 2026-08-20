import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * Le point de bascule fixtures/live tient sur une seule variable d'environnement
 * (`NEXT_PUBLIC_API_MODE`, lue une fois à l'import de `lib/env.ts`) — c'est le réglage qui
 * fait tourner toute l'application contre des données en mémoire ou contre l'API réelle
 * (`implementation.md`, « Décisions » : « chaque fonction de `lib/api/resources/**` bascule
 * vers `http.ts` sur un seul réglage »). Une régression ici casse silencieusement *tous*
 * les écrans à la fois, pas un composant isolé — c'est pourquoi il mérite un test dédié.
 */
describe("API_MODE (lib/env.ts)", () => {
  const ORIGINAL_ENV = process.env.NEXT_PUBLIC_API_MODE;

  afterEach(() => {
    if (ORIGINAL_ENV === undefined) delete process.env.NEXT_PUBLIC_API_MODE;
    else process.env.NEXT_PUBLIC_API_MODE = ORIGINAL_ENV;
    vi.resetModules();
  });

  it("vaut 'fixtures' par défaut quand la variable n'est pas posée", async () => {
    delete process.env.NEXT_PUBLIC_API_MODE;
    vi.resetModules();
    const { API_MODE } = await import("@/lib/env");
    expect(API_MODE).toBe("fixtures");
  });

  it("bascule en 'live' uniquement quand la variable vaut exactement 'live'", async () => {
    process.env.NEXT_PUBLIC_API_MODE = "live";
    vi.resetModules();
    const { API_MODE } = await import("@/lib/env");
    expect(API_MODE).toBe("live");
  });

  it("retombe sur 'fixtures' pour toute valeur qui n'est pas 'live' (ex. faute de frappe)", async () => {
    process.env.NEXT_PUBLIC_API_MODE = "Live"; // casse différente — piège classique
    vi.resetModules();
    const { API_MODE } = await import("@/lib/env");
    expect(API_MODE).toBe("fixtures");
  });
});
