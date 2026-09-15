// frontend/src/lib/api/memory.ts
//
// Request helpers for the `memory` kind's REST family (`/api/v1/memory/*`,
// spec memory FR-061). Partition lifecycle (delete) is deliberately absent: a
// partition is one `memory` Resource, so it goes through the kind-agnostic
// `DELETE /api/v1/resources/memory/{name}`, exactly like knowledge's
// collections.
//
// Transport via the shared `call` (agents/frontend.md §4); wire types in
// `memoryTypes.ts`.

import { call, enc } from "@/lib/api/call";
import type {
  AggregationResultOut,
  DeliveryStatusListOut,
  DeliveryStatusOut,
  FactListOut,
  FactOut,
  OrganiseResultOut,
  OverrideField,
  OverrideListOut,
  OverrideOut,
  OverridePatch,
  PartitionListOut,
} from "./memoryTypes";

export * from "./memoryTypes";

/** `/api/v1/memory` — the root every memory route hangs off. */
const ROOT = "/memory";

// --- partitions + facts -----------------------------------------------------

export function listPartitions(): Promise<PartitionListOut> {
  return call<PartitionListOut>(`${ROOT}/partitions`);
}

export function listFacts(partition: string): Promise<FactListOut> {
  return call<FactListOut>(`${ROOT}/partitions/${enc(partition)}/facts`);
}

export function getFact(partition: string, slug: string): Promise<FactOut> {
  return call<FactOut>(`${ROOT}/partitions/${enc(partition)}/facts/${enc(slug)}`);
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

// --- overrides (FR-040) ------------------------------------------------------

export function listOverrides(): Promise<OverrideListOut> {
  return call<OverrideListOut>(`${ROOT}/overrides`);
}

/** Set one or more of the four override fields on a fact. Fields not named
 * are left untouched — never send `false`/`""` here to clear one, that is
 * what `clearOverrideField` is for (mirrors the backend's PATCH semantics). */
export function patchOverride(factKey: string, patch: OverridePatch): Promise<OverrideOut> {
  return call<OverrideOut>(`${ROOT}/facts/${enc(factKey)}/override`, {
    method: "PATCH",
    body: patch,
  });
}

/** Clear one override field back to "no decision", leaving the other three
 * untouched. */
export function clearOverrideField(factKey: string, field: OverrideField): Promise<OverrideOut> {
  return call<OverrideOut>(`${ROOT}/facts/${enc(factKey)}/override?field=${enc(field)}`, {
    method: "DELETE",
  });
}

// --- delivery (FR-054/FR-055) ------------------------------------------------

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
