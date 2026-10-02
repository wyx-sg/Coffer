// src/lib/api/storage.ts — request functions for what Coffer keeps on disk and the rebuildable cache.
import { getApiClient, unwrap, unwrapOptional } from "@/lib/api/client";
import type { components } from "@/lib/api/types";

export type StorageSummary = components["schemas"]["StorageSummaryOut"];

export const storageApi = {
  summary: (): Promise<StorageSummary> => unwrap(getApiClient().GET("/storage")),
  /** Clear the rebuildable cache; resolves with the bytes freed. */
  clearCache: async (): Promise<number> =>
    (await unwrapOptional(getApiClient().POST("/storage/cache/clear")))?.cleared_bytes ?? 0,
};
