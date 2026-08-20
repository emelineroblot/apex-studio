/**
 * Persistance de la file d'upload — IndexedDB, pas `localStorage`.
 *
 * Le plan (§4, Frontend J1) évoque une file « persistée dans localStorage » ; en pratique
 * un `File`/`Blob` n'est **pas sérialisable en JSON** (`localStorage` est string-only).
 * IndexedDB, lui, supporte nativement le clonage structuré des `Blob`/`File` : c'est le
 * seul mécanisme qui permette une reprise **sans redemander les fichiers à
 * l'utilisateur** après un vrai rechargement de page (F5, onglet fermé/rouvert), ce que
 * `localStorage` ne pourrait offrir que pour les métadonnées. Décision documentée dans
 * `implementation.md`.
 */

/**
 * `rejected` : état terminal explicite pour un `413` (`quota_exceeded`/`file_too_large`,
 * revue J1 — voir `implementation.md`). Le backend crée quand même le média, en
 * quarantaine, **avant** de répondre l'erreur ; un rejeu de l'`Idempotency-Key` (retry
 * automatique ou bouton) renvoie alors un `200 duplicate=true` sur ce média déjà
 * quarantiné — jamais un vrai succès. Ne jamais retenter automatiquement ni proposer de
 * bouton « Réessayer » sur cet état, sous peine d'afficher « Envoyé » sur un média en
 * quarantaine.
 */
export type UploadItemStatus = "pending" | "uploading" | "done" | "error" | "rejected";

export type UploadItem = {
  /** Clé d'idempotence stable — envoyée telle quelle au backend (`Idempotency-Key`). */
  id: string;
  batchId: number;
  file: File;
  name: string;
  size: number;
  status: UploadItemStatus;
  attempts: number;
  mediaId?: number;
  error?: string;
};

export type BatchMeta = {
  batchId: number;
  shootingHintId: number | null;
  closed: boolean;
  createdAt: string;
};

const DB_NAME = "apex-upload-queue";
const DB_VERSION = 1;
const ITEMS_STORE = "items";
const META_STORE = "meta";
const META_KEY = "current";

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(ITEMS_STORE)) {
        db.createObjectStore(ITEMS_STORE, { keyPath: "id" });
      }
      if (!db.objectStoreNames.contains(META_STORE)) {
        db.createObjectStore(META_STORE);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function withStore<T>(
  storeName: string,
  mode: IDBTransactionMode,
  // L'API IDBRequest native n'unifie pas ses génériques entre put/get/delete ; le typage
  // précis vit dans `T`, résolu au niveau de l'appelant.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  fn: (store: IDBObjectStore) => IDBRequest<any> | void,
): Promise<T> {
  const db = await openDb();
  return new Promise<T>((resolve, reject) => {
    const tx = db.transaction(storeName, mode);
    const store = tx.objectStore(storeName);
    const request = fn(store);
    tx.oncomplete = () => resolve(request ? (request.result as T) : (undefined as T));
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}

export async function putItem(item: UploadItem): Promise<void> {
  await withStore(ITEMS_STORE, "readwrite", (store) => store.put(item));
}

export async function getAllItems(): Promise<UploadItem[]> {
  return withStore<UploadItem[]>(ITEMS_STORE, "readonly", (store) => store.getAll());
}

export async function deleteItem(id: string): Promise<void> {
  await withStore(ITEMS_STORE, "readwrite", (store) => store.delete(id));
}

export async function clearItems(): Promise<void> {
  await withStore(ITEMS_STORE, "readwrite", (store) => store.clear());
}

export async function setMeta(meta: BatchMeta | null): Promise<void> {
  await withStore(META_STORE, "readwrite", (store) =>
    meta ? store.put(meta, META_KEY) : store.delete(META_KEY),
  );
}

export async function getMeta(): Promise<BatchMeta | null> {
  const result = await withStore<BatchMeta | undefined>(META_STORE, "readonly", (store) =>
    store.get(META_KEY),
  );
  return result ?? null;
}
