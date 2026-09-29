// frontend/src/lib/api/memory.ts
//
// Request helpers for the `memory` kind's REST family (`/api/v1/memory/*`,
// spec memory "Cover memory management on REST and the CLI"). Partition lifecycle (delete) is
// deliberately absent: a partition is one `memory` Resource, so it goes through the kind-agnostic
// `DELETE /api/v1/resources/{uid}`, exactly like knowledge's collections.
//
// A partition is addressed by its uid. The delivery hook is not managed here:
// it is one part of an agent's Coffer connection (`agentsApi.connect`).
//
// Transport via the shared `call` (.agents/frontend.md §4); wire types in
// `memoryTypes.ts`.

import { call, enc } from "@/lib/api/call";
import type {
  AggregationResultOut,
  MemoryFileContentOut,
  MemoryFileTreeOut,
  PartitionListOut,
} from "./memoryTypes";

export * from "./memoryTypes";

/** `/api/v1/memory` — the root every memory route hangs off. */
const ROOT = "/memory";

// --- partitions -------------------------------------------------------------

export function listPartitions(): Promise<PartitionListOut> {
  return call<PartitionListOut>(`${ROOT}/partitions`);
}

// --- update (aggregation, then distil) ---------------------------------------

/** Update memory now (spec memory "Update memory in one action"): run
 * aggregation — the manual trigger for the background worker that otherwise
 * reads every registered agent's native memory on an interval — and then a
 * distil pass over every partition that gained raw entries. */
export function sync(): Promise<AggregationResultOut> {
  return call<AggregationResultOut>(`${ROOT}/sync`, { method: "POST" });
}

// --- a partition's own files ("Present partitions as a table and a file tree") ---

/** The partition directory as a tree — what the detail page browses. */
export function listPartitionFiles(partitionUid: string): Promise<MemoryFileTreeOut> {
  return call<MemoryFileTreeOut>(`${ROOT}/partitions/${enc(partitionUid)}/files`);
}

/** One file out of that directory, read-only. */
export function readPartitionFile(
  partitionUid: string,
  path: string,
): Promise<MemoryFileContentOut> {
  return call<MemoryFileContentOut>(
    `${ROOT}/partitions/${enc(partitionUid)}/files/content?path=${enc(path)}`,
  );
}
