// src/lib/api/storage.ts — request function for what Coffer keeps on disk.
import { getApiClient, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/types";

export type StorageSummary = components["schemas"]["StorageSummaryOut"];

export const storageApi = {
  summary: (): Promise<StorageSummary> => unwrap(getApiClient().GET("/storage")),
};
