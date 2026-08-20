import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

/**
 * La file d'upload est la pièce la plus « invisible » du frontend J1 : elle casse
 * silencieusement si un état terminal se comporte comme un état transitoire (ou l'inverse).
 * Deux cas ciblés explicitement :
 * - **rejet pour quota/taille (413)** : le média est déjà créé en quarantaine côté backend
 *   avant la réponse d'erreur (`routers/batches.py`) — un retry automatique renverrait un
 *   `200 duplicate=true` et l'item s'afficherait à tort comme « Envoyé ». L'état `rejected`
 *   doit être **terminal immédiatement**, sans passer par la boucle de retry/backoff.
 * - **échec réseau persistant** : doit, lui, épuiser ses tentatives et finir en `error` —
 *   un état terminal différent, pour ne pas masquer un vrai échec derrière le même badge
 *   qu'un rejet de quota.
 */

vi.mock("@/lib/api/resources/batches", () => ({
  create: vi.fn(),
  uploadFile: vi.fn(),
  close: vi.fn(),
  getStatus: vi.fn(),
}));

function makeFile(name = "photo.jpg"): File {
  return new File([new Uint8Array(10)], name, { type: "image/jpeg" });
}

describe("useUploadQueue — états terminaux", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(async () => {
    // Vide IndexedDB (fake-indexeddb, partagée entre tests via `vitest.setup.ts`) pour ne
    // pas faire fuiter un item d'un test au suivant via l'hydratation.
    const store = await import("@/lib/upload/db");
    await store.clearItems();
    await store.setMeta(null);
  });

  it("un 413 (quota dépassé) bascule l'item en 'rejected', jamais en retry automatique", async () => {
    const batchesApi = await import("@/lib/api/resources/batches");
    vi.mocked(batchesApi.create).mockResolvedValue({
      id: 1,
      status: "open",
      expected_count: 1,
    });
    vi.mocked(batchesApi.uploadFile).mockRejectedValue(
      new ApiError(413, {
        code: "quota_exceeded",
        message: "Le quota de stockage du shooting est dépassé.",
        detail: { media_id: 99, quota_bytes: 10 },
      }),
    );

    const { useUploadQueue } = await import("@/lib/upload/useUploadQueue");
    const { result } = renderHook(() => useUploadQueue());

    await waitFor(() => expect(result.current.hydrated).toBe(true));

    await act(async () => {
      await result.current.startBatch([makeFile()], 1);
    });

    await waitFor(() => {
      expect(result.current.items[0]?.status).toBe("rejected");
    });

    expect(result.current.items[0].mediaId).toBe(99);
    expect(result.current.rejectedCount).toBe(1);
    expect(result.current.errorCount).toBe(0);
    expect(batchesApi.uploadFile).toHaveBeenCalledTimes(1);

    // Un rejet ne doit jamais se retenter tout seul : on laisse la file au repos un peu et
    // on vérifie qu'aucun deuxième appel n'a été déclenché entre-temps.
    await new Promise((r) => setTimeout(r, 300));
    expect(batchesApi.uploadFile).toHaveBeenCalledTimes(1);
    expect(result.current.items[0]?.status).toBe("rejected");
  });

  it("un échec réseau persistant épuise ses tentatives et finit en 'error' (pas 'rejected')", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const batchesApi = await import("@/lib/api/resources/batches");
      vi.mocked(batchesApi.create).mockResolvedValue({
        id: 2,
        status: "open",
        expected_count: 1,
      });
      vi.mocked(batchesApi.uploadFile).mockRejectedValue(new Error("network down"));

      const { useUploadQueue } = await import("@/lib/upload/useUploadQueue");
      const { result } = renderHook(() => useUploadQueue());

      await vi.waitFor(() => expect(result.current.hydrated).toBe(true));

      await act(async () => {
        await result.current.startBatch([makeFile("flaky.jpg")], 2);
      });

      // 5 tentatives max, backoff exponentiel (800ms, 1600ms, 3200ms, 6400ms) : on avance
      // le temps simulé jusqu'à épuisement plutôt que d'attendre en temps réel.
      await vi.advanceTimersByTimeAsync(20_000);

      expect(result.current.items[0]?.status).toBe("error");
      expect(result.current.errorCount).toBe(1);
      expect(result.current.rejectedCount).toBe(0);
      expect(batchesApi.uploadFile).toHaveBeenCalledTimes(5);
    } finally {
      vi.useRealTimers();
    }
  });
});
