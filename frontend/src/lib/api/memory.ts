// frontend/src/lib/api/memory.ts
//
// Request helpers for the memory sync (`/api/v1/memory/sync/*`, spec memory
// "Manage memory sync in the web UI and on the command line"): its state, Sync now, the pending
// preview's Write and Cancel, Undo sync…, the person's answer to "Codex
// imports Claude Code's memories itself", one project's memories and Curate
// now. The sync's switch and interval are the internal engine's `memory_sync`
// pass (`internalEngineApi.setUpkeep`), not a route here.
//
// Transport via the typed client (.agents/frontend.md §4); wire types in
// `memoryTypes.ts`, aliases of the generated contract.
import { getApiClient, unwrap, unwrapVoid } from "@/lib/api/client";
import type { CurateResult, HubEntryList, MemorySyncReport, MemorySyncState } from "./memoryTypes";

export * from "./memoryTypes";

export function getSyncState(): Promise<MemorySyncState> {
  return unwrap(getApiClient().GET("/memory/sync/state"));
}

/** Sync now: 409 `MEMORY_SYNC_RUNNING` while a sync runs. */
export function runSync(): Promise<MemorySyncReport> {
  return unwrap(getApiClient().POST("/memory/sync/run"));
}

/** Write exactly what the pending preview listed. */
export function writePreview(): Promise<MemorySyncReport> {
  return unwrap(getApiClient().POST("/memory/sync/preview/write"));
}

/** Drop the pending preview; nothing is written into the agents. */
export function cancelPreview(): Promise<void> {
  return unwrapVoid(getApiClient().POST("/memory/sync/preview/cancel"));
}

/** Undo sync…: remove every copy Coffer wrote on this machine that the agent
 *  has not changed, and turn automatic sync off. */
export function undoSync(): Promise<MemorySyncReport> {
  return unwrap(getApiClient().POST("/memory/sync/undo"));
}

/** `true` when Codex imports Claude Code's memories itself, `null` to forget the answer. */
export function setCodexImport(value: boolean | null): Promise<void> {
  return unwrapVoid(getApiClient().PUT("/memory/sync/codex-import", { body: { value } }));
}

/** One project's memories (`""` for global ones), each with its copy state here. */
export function listEntries(project: string): Promise<HubEntryList> {
  return unwrap(getApiClient().GET("/memory/sync/entries", { params: { query: { project } } }));
}

/** Curate now: start the agent without a terminal, asking it to consolidate its own memory. */
export function curate(agentType: string): Promise<CurateResult> {
  return unwrap(getApiClient().POST("/memory/sync/curate", { body: { agent_type: agentType } }));
}
