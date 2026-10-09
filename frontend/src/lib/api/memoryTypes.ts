// frontend/src/lib/api/memoryTypes.ts
//
// Wire types of the memory sync (`/api/v1/memory/sync/*`), every one an alias
// of the generated contract (`generated/memory.ts`, from `openspec/specs/memory`'s
// `api.openapi.yaml`, itself generated from
// `backend/coffer/surfaces/http/memory/sync_routes.py`). Coffer keeps every
// memory an agent wrote for itself in a hub in the vault and writes each one
// into the person's other agents; there is no write shape for a memory's text:
// the person edits memory in the agent's own memory directory.
import type { components as MemoryWire } from "@/lib/api/generated/memory";

type Schemas = MemoryWire["schemas"];

/** What the Memory page reads: the switch-independent facts of the sync, the
 *  pending preview, the hub's projects and this machine's agents. */
export type MemorySyncState = Schemas["MemorySyncStateOut"];

/** One local agent: its writer's status, its own curation, and the copies
 *  Coffer holds in it on this machine, by state. */
export type SyncAgent = Schemas["SyncAgentOut"];

/** One project in the hub: how many memories, from which agent types, and
 *  where it is checked out here (`null`: held back). */
export type SyncProject = Schemas["SyncProjectOut"];

/** What one sync, write or undo did (the `memory_synced` details). */
export type MemorySyncReport = Schemas["MemorySyncReportOut"];

/** One hub entry with, per local agent type, its copy's state here. */
export type HubEntry = Schemas["HubEntryOut"];
export type HubEntryList = Schemas["HubEntryListOut"];

export type CurateResult = Schemas["CurateOut"];
