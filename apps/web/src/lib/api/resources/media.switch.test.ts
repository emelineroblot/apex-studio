import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * Vérifie le point de bascule lui-même, pas seulement la valeur de `API_MODE` (voir
 * `lib/env.test.ts`) : que `resources/media.ts::list` appelle réellement l'implémentation
 * fixtures OU l'implémentation HTTP réelle selon `NEXT_PUBLIC_API_MODE`, jamais les deux,
 * jamais aucune. C'est la fonction que tous les écrans de la bibliothèque consomment
 * (`app/(app)/library/page.tsx`) — une bascule cassée servirait des fixtures en
 * production, silencieusement.
 */
describe("resources/media.ts — bascule fixtures/live", () => {
  const ORIGINAL_ENV = process.env.NEXT_PUBLIC_API_MODE;

  afterEach(() => {
    if (ORIGINAL_ENV === undefined) delete process.env.NEXT_PUBLIC_API_MODE;
    else process.env.NEXT_PUBLIC_API_MODE = ORIGINAL_ENV;
    vi.resetModules();
    vi.doUnmock("@/lib/api/http");
    vi.doUnmock("@/lib/api/fixtures/media");
    vi.doUnmock("@/lib/api/fixtures/access");
  });

  it("mode fixtures (défaut) : list() appelle les fixtures, jamais apiRequest", async () => {
    delete process.env.NEXT_PUBLIC_API_MODE;
    vi.resetModules();

    const apiRequest = vi.fn().mockRejectedValue(new Error("apiRequest ne doit pas être appelé"));
    vi.doMock("@/lib/api/http", () => ({ apiRequest, apiFetchBlob: vi.fn() }));
    const fixturesList = vi.fn().mockResolvedValue({ items: [], next_cursor: null });
    vi.doMock("@/lib/api/fixtures/media", () => ({
      list: fixturesList,
      get: vi.fn(),
      attach: vi.fn(),
      previewUrl: vi.fn(),
    }));
    vi.doMock("@/lib/api/fixtures/access", () => ({
      currentUserId: () => 1,
      visibleShootingIdsForCurrentUser: () => null,
    }));

    const media = await import("@/lib/api/resources/media");
    await media.list({ shooting_id: 1 });

    expect(fixturesList).toHaveBeenCalledTimes(1);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it("mode live : list() appelle apiRequest('/media', ...), jamais les fixtures", async () => {
    process.env.NEXT_PUBLIC_API_MODE = "live";
    vi.resetModules();

    const apiRequest = vi.fn().mockResolvedValue({ items: [], next_cursor: null });
    vi.doMock("@/lib/api/http", () => ({ apiRequest, apiFetchBlob: vi.fn() }));
    const fixturesList = vi.fn().mockRejectedValue(new Error("les fixtures ne doivent pas être appelées"));
    vi.doMock("@/lib/api/fixtures/media", () => ({
      list: fixturesList,
      get: vi.fn(),
      attach: vi.fn(),
      previewUrl: vi.fn(),
    }));
    vi.doMock("@/lib/api/fixtures/access", () => ({
      currentUserId: () => 1,
      visibleShootingIdsForCurrentUser: () => null,
    }));

    const media = await import("@/lib/api/resources/media");
    await media.list({ shooting_id: 1 });

    expect(apiRequest).toHaveBeenCalledTimes(1);
    expect(apiRequest.mock.calls[0][0]).toBe("/media");
    expect(fixturesList).not.toHaveBeenCalled();
  });
});
