// frontend/src/lib/api/vault.ts — request functions for /api/v1/vault/*
//
// The history of a vault file or folder (spec vault-storage "Show and restore
// any version of a vault file or folder"): its versions newest first, each
// naming its writer; a version's diff, file by file, against the version
// before it or against the path as it is now; and restoring a version, which
// writes a NEW version through the same checks every vault write passes and
// is refused when the path changed since its history was read. A path is
// vault-relative; a folder ends in `/` (`skills/pdf/`).
//
// Every wire type is an alias of the generated schemas; requests go through
// the generated client (.agents/frontend.md §4).
import { getApiClient, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/types";

type Schemas = components["schemas"];

export type VaultVersionOut = Schemas["VaultVersionOut"];
export type VaultHistoryOut = Schemas["VaultHistoryOut"];
export type VaultDiffOut = Schemas["VaultDiffOut"];
export type VaultFileDiffOut = Schemas["VaultFileDiffOut"];
export type VaultRestoreIn = Schemas["VaultRestoreIn"];
export type VaultRestoreOut = Schemas["VaultRestoreOut"];
export type VaultDiffAgainst = VaultDiffOut["against"];

/** How many versions a History tab reads: the API's ceiling. */
const HISTORY_LIMIT = 200;

export const vaultApi = {
  /** A file's or folder's (`…/`) versions, newest first. */
  history: (path: string, limit = HISTORY_LIMIT): Promise<VaultHistoryOut> =>
    unwrap(getApiClient().GET("/vault/history", { params: { query: { path, limit } } })),
  /** What one version changed, or how the path differs now from it, file by file. */
  diff: (path: string, version: string, against: VaultDiffAgainst): Promise<VaultDiffOut> =>
    unwrap(getApiClient().GET("/vault/diff", { params: { query: { path, version, against } } })),
  /** Put a version back, as a new version naming you. */
  restore: (body: VaultRestoreIn): Promise<VaultRestoreOut> =>
    unwrap(getApiClient().POST("/vault/restore", { body })),
};
