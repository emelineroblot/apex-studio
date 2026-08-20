/**
 * Corps d'erreur uniforme du backend (§ Contrat d'API, plan) :
 * `{"code": "<slug>", "message": "<français>", "detail": {...}}`.
 * Confirmé dans `services/api/src/apex/main.py` (`http_exception_handler`,
 * `validation_exception_handler`) et `routers/_common.py` (`not_implemented`, 501).
 */
export type ApiErrorBody = {
  code: string;
  message: string;
  detail?: unknown;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: unknown;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message || `Erreur API (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.detail = body.detail;
  }

  get isNotImplemented(): boolean {
    return this.status === 501 || this.code === "not_implemented";
  }

  get isAuthError(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  /** `413` — quota de shooting dépassé ou fichier trop volumineux (`routers/batches.py`).
   * Le média est déjà créé, en quarantaine, avant la réponse d'erreur : jamais retentable
   * automatiquement, un rejeu renverrait un faux succès idempotent. */
  get isPayloadRejected(): boolean {
    return this.status === 413;
  }
}

/** Message générique et sobre pour un état d'erreur affiché à l'écran. */
export function friendlyErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.isNotImplemented) {
      return "Cette fonctionnalité n'est pas encore branchée côté serveur.";
    }
    return error.message || "Une erreur est survenue.";
  }
  if (error instanceof Error) return error.message;
  return "Une erreur inattendue est survenue.";
}
