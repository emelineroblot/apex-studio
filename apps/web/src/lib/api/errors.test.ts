import { describe, expect, it } from "vitest";
import { ApiError, friendlyErrorMessage } from "@/lib/api/errors";

describe("ApiError", () => {
  it("isPayloadRejected est vrai uniquement pour un 413 (quota/taille dépassés)", () => {
    const rejected = new ApiError(413, { code: "quota_exceeded", message: "Quota dépassé." });
    expect(rejected.isPayloadRejected).toBe(true);
    expect(rejected.isNotFound).toBe(false);
    expect(rejected.isForbidden).toBe(false);
  });

  it("isPayloadRejected est faux pour les autres statuts (404, 500, 200)", () => {
    for (const status of [200, 401, 403, 404, 409, 422, 500]) {
      const err = new ApiError(status, { code: "x", message: "x" });
      expect(err.isPayloadRejected, `status ${status}`).toBe(false);
    }
  });

  it("isNotFound / isForbidden / isAuthError sont mutuellement exclusifs sur leur statut", () => {
    expect(new ApiError(404, { code: "not_found", message: "m" }).isNotFound).toBe(true);
    expect(new ApiError(403, { code: "forbidden", message: "m" }).isForbidden).toBe(true);
    expect(new ApiError(401, { code: "unauthorized", message: "m" }).isAuthError).toBe(true);
  });

  it("isNotImplemented détecte aussi bien le statut 501 que le code métier", () => {
    expect(new ApiError(501, { code: "x", message: "m" }).isNotImplemented).toBe(true);
    expect(new ApiError(200, { code: "not_implemented", message: "m" }).isNotImplemented).toBe(
      true,
    );
    expect(new ApiError(404, { code: "not_found", message: "m" }).isNotImplemented).toBe(false);
  });

  it("conserve le détail structuré (ex. media_id d'un média quarantiné sur 413)", () => {
    const err = new ApiError(413, {
      code: "quota_exceeded",
      message: "Quota dépassé.",
      detail: { media_id: 42, quota_bytes: 10 },
    });
    expect(err.detail).toEqual({ media_id: 42, quota_bytes: 10 });
  });
});

describe("friendlyErrorMessage", () => {
  it("restitue le message français du backend pour une ApiError", () => {
    const err = new ApiError(413, { code: "quota_exceeded", message: "Le quota est dépassé." });
    expect(friendlyErrorMessage(err)).toBe("Le quota est dépassé.");
  });

  it("donne un message générique pour une fonctionnalité non implémentée (501)", () => {
    const err = new ApiError(501, { code: "not_implemented", message: "" });
    expect(friendlyErrorMessage(err)).toBe(
      "Cette fonctionnalité n'est pas encore branchée côté serveur.",
    );
  });

  it("retombe sur un message générique pour une erreur non-ApiError", () => {
    expect(friendlyErrorMessage("boom")).toBe("Une erreur inattendue est survenue.");
    expect(friendlyErrorMessage(new Error("réseau coupé"))).toBe("réseau coupé");
  });
});
