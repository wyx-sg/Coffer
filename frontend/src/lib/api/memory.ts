// frontend/src/lib/api/memory.ts
//
// Request helpers for the `memory` kind's REST family (`/api/v1/memory/*`,
// spec memory "Cover memory management on REST and the CLI"). Partition
// deletion is deliberately absent: a partition is one `memory` Resource, so it
// goes through the kind-agnostic `DELETE /api/v1/resources/{uid}`.
//
// A partition is addressed by its uid. The delivery hook is not managed here:
// it is one part of an agent's Coffer connection (`agentsApi.connect`).
//
// Transport via the shared `call` (.agents/frontend.md §4); wire types in
// `memoryTypes.ts`, aliases of the generated contract.

import { call, enc } from "@/lib/api/call";
import type {
  AggregationResultOut,
  DeliveredOut,
  DeliveryOverviewOut,
  MemoryFileTreeOut,
  NoteListOut,
  NoteOut,
  PartitionListOut,
  ReadingOut,
  RetiredListOut,
} from "./memoryTypes";

export * from "./memoryTypes";

/** `/api/v1/memory` — the root every memory route hangs off. */
const ROOT = "/memory";

const partitionPath = (uid: string) => `${ROOT}/partitions/${enc(uid)}`;

// --- partitions -------------------------------------------------------------

export function listPartitions(): Promise<PartitionListOut> {
  return call<PartitionListOut>(`${ROOT}/partitions`);
}

// --- update (aggregation, then distil) ---------------------------------------

/** Update memory now (spec memory "Update memory in one action"): read every
 * registered agent's native memory, then distil every partition that gained
 * raw entries. */
export function sync(): Promise<AggregationResultOut> {
  return call<AggregationResultOut>(`${ROOT}/sync`, { method: "POST" });
}

// --- one partition's memories ("Present a partition as its memories") -------

export function listNotes(uid: string): Promise<NoteListOut> {
  return call<NoteListOut>(`${partitionPath(uid)}/notes`);
}

export function getNote(uid: string, slug: string): Promise<NoteOut> {
  return call<NoteOut>(`${partitionPath(uid)}/notes/${enc(slug)}`);
}

export function listRetired(uid: string): Promise<RetiredListOut> {
  return call<RetiredListOut>(`${partitionPath(uid)}/retired`);
}

/** The partition directory — read only for the absolute paths that open-in-
 *  editor and reveal need. */
export function listPartitionFiles(uid: string): Promise<MemoryFileTreeOut> {
  return call<MemoryFileTreeOut>(`${partitionPath(uid)}/files`);
}

// --- delivery (web-ui "Show memory delivery on the Memory page") -------------

/** The exact session-start text each connected agent receives in the
 *  partition's project. */
export function getDelivered(uid: string): Promise<DeliveredOut> {
  return call<DeliveredOut>(`${partitionPath(uid)}/delivered`);
}

/** Per agent, deliveries, memories read and the last delivery over the last
 *  seven days. */
/** When the agents' memory was last read, and which agents failed. */
export function getReading(): Promise<ReadingOut> {
  return call<ReadingOut>("/memory/reading");
}

export function getDeliveries(): Promise<DeliveryOverviewOut> {
  return call<DeliveryOverviewOut>(`${ROOT}/deliveries`);
}
