// frontend/src/lib/api/vault.ts — request functions for /api/v1/vault/*
//
// The vault's history is git's: Coffer lists, diffs and restores no version.
// What it serves is the hand-off of an earlier version (spec vault-storage
// "Hand restoring an earlier version of a vault file to an agent"): the path's
// absolute location, the `git log` command and the prompt for the person's
// agent. A path is vault-relative; a folder ends in `/` (`skills/pdf/`).
//
// Every wire type is an alias of the generated schemas; requests go through
// the generated client (.agents/frontend.md §4).
import { getApiClient, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/types";

type Schemas = components["schemas"];

export type VaultHistoryHandoffOut = Schemas["VaultHistoryHandoffOut"];

export const vaultApi = {
  /** The restore hand-off for a file or folder, optionally to how it was at `at`. */
  historyHandoff: (path: string, at?: string | null): Promise<VaultHistoryHandoffOut> =>
    unwrap(getApiClient().POST("/vault/history/handoff", { body: { path, at: at ?? null } })),
};
