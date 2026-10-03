// frontend/src/lib/api/vault.ts — request functions for /api/v1/vault/*
//
// The history of any vault file or folder (spec vault-storage "Show, compare
// and restore any version of a vault file"): its versions newest first, each
// naming its writer; the diff one version made to one file; and restoring a
// version, which writes a NEW version through the same compare-and-swap every
// vault write passes — a file restore states the fingerprint of what it last
// read, a folder restore is compared file by file against the current
// version. A path is vault-relative; a folder ends in `/` (`skills/pdf/`).
//
// Every wire type is an alias of the generated schemas; requests go through
// the generated client (.agents/frontend.md §4).
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";

type Schemas = components["schemas"];

export type VaultVersionOut = Schemas["VaultVersionOut"];
export type VaultHistoryOut = Schemas["VaultHistoryOut"];
export type VaultDiffOut = Schemas["VaultDiffOut"];
export type VaultRestoreIn = Schemas["VaultRestoreIn"];
export type VaultRestoreOut = Schemas["VaultRestoreOut"];

/** How many versions a History tab reads: the API's ceiling. */
const HISTORY_LIMIT = 200;

function must<T>(data: T | undefined, what: string): T {
  if (data === undefined) throw new ApiError("INTERNAL_ERROR", `empty ${what} response`);
  return data;
}

export const vaultApi = {
  /** A file's or folder's (`…/`) versions, newest first. */
  history: async (path: string, limit = HISTORY_LIMIT): Promise<VaultHistoryOut> => {
    const { data, error } = await getApiClient().GET("/vault/history", {
      params: { query: { path, limit } },
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "history read failed");
    return must(data, "history");
  },
  /** What one version did to one file, as a unified diff. */
  diff: async (path: string, version: string): Promise<VaultDiffOut> => {
    const { data, error } = await getApiClient().GET("/vault/diff", {
      params: { query: { path, version } },
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "diff read failed");
    return must(data, "diff");
  },
  /** Put a version back, as a new version naming you. */
  restore: async (body: VaultRestoreIn): Promise<VaultRestoreOut> => {
    const { data, error } = await getApiClient().POST("/vault/restore", { body });
    if (error) throwApiError(error, "INTERNAL_ERROR", "restore failed");
    return must(data, "restore");
  },
};
