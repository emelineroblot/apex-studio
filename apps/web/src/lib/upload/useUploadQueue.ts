"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import * as batchesApi from "@/lib/api/resources/batches";
import { friendlyErrorMessage } from "@/lib/api/errors";
import * as store from "@/lib/upload/db";
import type { BatchMeta, UploadItem } from "@/lib/upload/db";

const CONCURRENCY = 3;
const MAX_ATTEMPTS = 5;
const BACKOFF_BASE_MS = 800;

function idempotencyKeyFor(batchId: number, file: File): string {
  return `${batchId}:${file.name}:${file.size}:${file.lastModified}`;
}

export function useUploadQueue() {
  const [items, setItems] = useState<UploadItem[]>([]);
  const [meta, setMeta] = useState<BatchMeta | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [running, setRunning] = useState(false);

  const activeCountRef = useRef(0);
  const itemsRef = useRef<UploadItem[]>([]);
  const runningRef = useRef(false);
  const pumpRef = useRef<() => Promise<void>>(async () => {});
  itemsRef.current = items;

  // Hydratation depuis IndexedDB — c'est ce qui permet la reprise après un vrai rechargement.
  useEffect(() => {
    let cancelled = false;
    Promise.all([store.getAllItems(), store.getMeta()]).then(([storedItems, storedMeta]) => {
      if (cancelled) return;
      // Un item resté « uploading » lors d'une coupure redevient « pending » — reprenable.
      const normalized = storedItems.map((it) =>
        it.status === "uploading" ? { ...it, status: "pending" as const } : it,
      );
      setItems(normalized);
      setMeta(storedMeta);
      setHydrated(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const persistItem = useCallback((item: UploadItem) => {
    setItems((prev) => {
      const next = prev.some((p) => p.id === item.id)
        ? prev.map((p) => (p.id === item.id ? item : p))
        : [...prev, item];
      itemsRef.current = next;
      return next;
    });
    void store.putItem(item);
  }, []);

  const uploadOne = useCallback(
    async (item: UploadItem) => {
      const uploading: UploadItem = { ...item, status: "uploading" };
      persistItem(uploading);
      try {
        const result = await batchesApi.uploadFile(item.batchId, item.file, item.id);
        persistItem({ ...uploading, status: "done", mediaId: result.media_id, error: undefined });
      } catch (err) {
        const attempts = item.attempts + 1;
        if (attempts >= MAX_ATTEMPTS) {
          persistItem({ ...uploading, status: "error", attempts, error: friendlyErrorMessage(err) });
        } else {
          persistItem({ ...uploading, status: "pending", attempts, error: friendlyErrorMessage(err) });
          const backoff = BACKOFF_BASE_MS * 2 ** (attempts - 1);
          setTimeout(() => {
            void pumpRef.current();
          }, backoff);
        }
      }
    },
    [persistItem],
  );

  const pump = useCallback(async () => {
    if (runningRef.current) return;
    runningRef.current = true;
    setRunning(true);
    try {
      for (;;) {
        const pending = itemsRef.current.filter((it) => it.status === "pending");
        if (pending.length === 0 && activeCountRef.current === 0) break;
        const capacity = CONCURRENCY - activeCountRef.current;
        if (capacity <= 0 || pending.length === 0) {
          if (activeCountRef.current === 0) break;
          await new Promise((r) => setTimeout(r, 150));
          continue;
        }
        const batch = pending.slice(0, capacity);
        activeCountRef.current += batch.length;
        void Promise.all(
          batch.map(async (item) => {
            await uploadOne(item);
            activeCountRef.current -= 1;
          }),
        );
        await new Promise((r) => setTimeout(r, 120));
      }
    } finally {
      runningRef.current = false;
      setRunning(false);
    }
  }, [uploadOne]);
  pumpRef.current = pump;

  const startBatch = useCallback(
    async (files: File[], shootingHintId: number | null) => {
      const created = await batchesApi.create({
        expected_count: files.length,
        shooting_hint_id: shootingHintId,
      });
      const newMeta: BatchMeta = {
        batchId: created.id,
        shootingHintId,
        closed: false,
        createdAt: new Date().toISOString(),
      };
      await store.setMeta(newMeta);
      setMeta(newMeta);

      const newItems: UploadItem[] = files.map((file) => ({
        id: idempotencyKeyFor(created.id, file),
        batchId: created.id,
        file,
        name: file.name,
        size: file.size,
        status: "pending",
        attempts: 0,
      }));
      for (const item of newItems) await store.putItem(item);
      setItems(newItems);
      itemsRef.current = newItems;
      void pump();
      return created.id;
    },
    [pump],
  );

  const addFiles = useCallback(
    (files: File[]) => {
      if (!meta) return;
      const newItems: UploadItem[] = files.map((file) => ({
        id: idempotencyKeyFor(meta.batchId, file),
        batchId: meta.batchId,
        file,
        name: file.name,
        size: file.size,
        status: "pending",
        attempts: 0,
      }));
      for (const item of newItems) void store.putItem(item);
      setItems((prev) => {
        const next = [...prev, ...newItems];
        itemsRef.current = next;
        return next;
      });
      void pump();
    },
    [meta, pump],
  );

  const retryItem = useCallback(
    (id: string) => {
      const item = itemsRef.current.find((it) => it.id === id);
      if (!item) return;
      persistItem({ ...item, status: "pending", attempts: 0, error: undefined });
      void pump();
    },
    [persistItem, pump],
  );

  const resume = useCallback(() => {
    void pump();
  }, [pump]);

  const closeBatch = useCallback(async () => {
    if (!meta) return;
    await batchesApi.close(meta.batchId);
    const updated = { ...meta, closed: true };
    await store.setMeta(updated);
    setMeta(updated);
  }, [meta]);

  const abandon = useCallback(async () => {
    await store.clearItems();
    await store.setMeta(null);
    setItems([]);
    itemsRef.current = [];
    setMeta(null);
  }, []);

  const doneCount = items.filter((it) => it.status === "done").length;
  const errorCount = items.filter((it) => it.status === "error").length;
  const pendingOrUploadingCount = items.filter(
    (it) => it.status === "pending" || it.status === "uploading",
  ).length;

  return {
    hydrated,
    items,
    meta,
    running,
    doneCount,
    errorCount,
    pendingOrUploadingCount,
    total: items.length,
    startBatch,
    addFiles,
    retryItem,
    resume,
    closeBatch,
    abandon,
  };
}
