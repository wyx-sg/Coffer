// frontend/src/lib/api/memory.ts
//
// Request helpers for the `memory` kind's REST family (`/api/v1/memory/*`,
// spec memory "Cover memory management on REST and the CLI"). Partition lifecycle (delete) is
// deliberately absent: a partition is one `memory` Resource, so it goes through the kind-agnostic
// `DELETE /api/v1/resources/{uid}`, exactly like knowledge's collections.
//
// A partition is addressed by its uid and an agent by ITS uid — delivery is a
// route about one agent, and the uid is also what goes into the hook command
// the install writes, so the entry keeps naming that agent through any number
// of relabels.
//
// Transport via the shared `call` (.agents/frontend.md §4); wire types in
// `memoryTypes.ts`.

import { call, enc } from "@/lib/api/call";
import type {
  AggregationResultOut,
  DeliveryStatusListOut,
  DeliveryStatusOut,
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
 * distil pass over every partition that gained raw entries. The per-partition
 * distil route exists for the CLI; the UI only ever asks for both at once. */
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
// --- delivery ("Install delivery hooks explicitly and removably") ---------------

/** Every agent delivery can be installed for, and whether it is. Omit
 * `agentUid` to list all of them. */
export function listDelivery(agentUid?: string): Promise<DeliveryStatusListOut> {
  const qs = agentUid ? `?agent_uid=${enc(agentUid)}` : "";
  return call<DeliveryStatusListOut>(`${ROOT}/delivery${qs}`);
}

export function installDelivery(agentUid: string): Promise<DeliveryStatusOut> {
  return call<DeliveryStatusOut>(`${ROOT}/delivery/${enc(agentUid)}/install`, { method: "POST" });
}

export function removeDelivery(agentUid: string): Promise<DeliveryStatusOut> {
  return call<DeliveryStatusOut>(`${ROOT}/delivery/${enc(agentUid)}`, { method: "DELETE" });
}
