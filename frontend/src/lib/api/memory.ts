// frontend/src/lib/api/memory.ts
//
// Request helpers for the `memory` kind's REST family (`/api/v1/memory/*`,
// spec memory FR-028). Partition lifecycle (delete) is deliberately absent: a
// partition is one `memory` Resource, so it goes through the kind-agnostic
// `DELETE /api/v1/resources/memory/{name}`, exactly like knowledge's
// collections.
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
  OrganiseResultOut,
  PartitionListOut,
} from "./memoryTypes";

export * from "./memoryTypes";

/** `/api/v1/memory` — the root every memory route hangs off. */
const ROOT = "/memory";

// --- partitions -------------------------------------------------------------

export function listPartitions(): Promise<PartitionListOut> {
  return call<PartitionListOut>(`${ROOT}/partitions`);
}

// --- aggregation + organise --------------------------------------------------

/** Run aggregation now — the manual trigger for the background worker that
 * otherwise reads every registered agent's native memory on an interval. */
export function sync(): Promise<AggregationResultOut> {
  return call<AggregationResultOut>(`${ROOT}/sync`, { method: "POST" });
}

/** Run the organise pass over one partition: merge duplicates, propose
 * supersessions and conflicts, rewrite the digest. */
export function organise(partition: string): Promise<OrganiseResultOut> {
  return call<OrganiseResultOut>(`${ROOT}/partitions/${enc(partition)}/organise`, {
    method: "POST",
  });
}

// --- a partition's own files (FR-029) ----------------------------------------

/** The partition directory as a tree — what the detail page browses. */
export function listPartitionFiles(partition: string): Promise<MemoryFileTreeOut> {
  return call<MemoryFileTreeOut>(`${ROOT}/partitions/${enc(partition)}/files`);
}

/** One file out of that directory, read-only. */
export function readPartitionFile(
  partition: string,
  path: string,
): Promise<MemoryFileContentOut> {
  return call<MemoryFileContentOut>(
    `${ROOT}/partitions/${enc(partition)}/files/content?path=${enc(path)}`,
  );
}
// --- delivery (FR-025/FR-026) ------------------------------------------------

/** Every agent delivery can be installed for, and whether it is. Omit
 * `agent` to list all of them. */
export function listDelivery(agent?: string): Promise<DeliveryStatusListOut> {
  const qs = agent ? `?agent=${enc(agent)}` : "";
  return call<DeliveryStatusListOut>(`${ROOT}/delivery${qs}`);
}

export function installDelivery(agent: string): Promise<DeliveryStatusOut> {
  return call<DeliveryStatusOut>(`${ROOT}/delivery/${enc(agent)}/install`, { method: "POST" });
}

export function removeDelivery(agent: string): Promise<DeliveryStatusOut> {
  return call<DeliveryStatusOut>(`${ROOT}/delivery/${enc(agent)}`, { method: "DELETE" });
}
