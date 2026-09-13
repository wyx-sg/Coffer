// frontend/src/kinds/memory/api.ts
//
// Hand-written fetch helpers for the `memory` kind's REST family
// (`/api/v1/memory/*`, spec memory FR-061). Partition lifecycle (delete) is
// deliberately absent: a partition is one `memory` Resource, so it goes
// through the kind-agnostic `DELETE /api/v1/resources/memory/{name}`, exactly
// like knowledge's collections.

import { checkOk, enc, headers, memoryRoot } from "./client";
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
} from "./types";

export * from "./types";

// --- partitions + facts -----------------------------------------------------

export async function listPartitions(): Promise<PartitionListOut> {
  const r = await fetch(`${memoryRoot()}/partitions`, { headers: headers() });
  await checkOk(r);
  return (await r.json()) as PartitionListOut;
}

export async function listFacts(partition: string): Promise<FactListOut> {
  const r = await fetch(`${memoryRoot()}/partitions/${enc(partition)}/facts`, {
    headers: headers(),
  });
  await checkOk(r);
  return (await r.json()) as FactListOut;
}

export async function getFact(partition: string, slug: string): Promise<FactOut> {
  const r = await fetch(`${memoryRoot()}/partitions/${enc(partition)}/facts/${enc(slug)}`, {
    headers: headers(),
  });
  await checkOk(r);
  return (await r.json()) as FactOut;
}

// --- aggregation + organise --------------------------------------------------

/** Run aggregation now — the manual trigger for the background worker that
 * otherwise reads every registered agent's native memory on an interval. */
export async function sync(): Promise<AggregationResultOut> {
  const r = await fetch(`${memoryRoot()}/sync`, { method: "POST", headers: headers() });
  await checkOk(r);
  return (await r.json()) as AggregationResultOut;
}

/** Run the organise pass over one partition: merge duplicates, propose
 * supersessions and conflicts, rewrite the digest. */
export async function organise(partition: string): Promise<OrganiseResultOut> {
  const r = await fetch(`${memoryRoot()}/partitions/${enc(partition)}/organise`, {
    method: "POST",
    headers: headers(),
  });
  await checkOk(r);
  return (await r.json()) as OrganiseResultOut;
}

// --- overrides (FR-040) ------------------------------------------------------

export async function listOverrides(): Promise<OverrideListOut> {
  const r = await fetch(`${memoryRoot()}/overrides`, { headers: headers() });
  await checkOk(r);
  return (await r.json()) as OverrideListOut;
}

/** Set one or more of the four override fields on a fact. Fields not named
 * are left untouched — never send `false`/`""` here to clear one, that is
 * what `clearOverrideField` is for (mirrors the backend's PATCH semantics). */
export async function patchOverride(factKey: string, patch: OverridePatch): Promise<OverrideOut> {
  const r = await fetch(`${memoryRoot()}/facts/${enc(factKey)}/override`, {
    method: "PATCH",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  await checkOk(r);
  return (await r.json()) as OverrideOut;
}

/** Clear one override field back to "no decision", leaving the other three
 * untouched. */
export async function clearOverrideField(
  factKey: string,
  field: OverrideField,
): Promise<OverrideOut> {
  const r = await fetch(`${memoryRoot()}/facts/${enc(factKey)}/override?field=${enc(field)}`, {
    method: "DELETE",
    headers: headers(),
  });
  await checkOk(r);
  return (await r.json()) as OverrideOut;
}

// --- delivery (FR-054/FR-055) ------------------------------------------------

/** Every agent delivery can be installed for, and whether it is. Omit
 * `agent` to list all of them. */
export async function listDelivery(agent?: string): Promise<DeliveryStatusListOut> {
  const qs = agent ? `?agent=${enc(agent)}` : "";
  const r = await fetch(`${memoryRoot()}/delivery${qs}`, { headers: headers() });
  await checkOk(r);
  return (await r.json()) as DeliveryStatusListOut;
}

export async function installDelivery(agent: string): Promise<DeliveryStatusOut> {
  const r = await fetch(`${memoryRoot()}/delivery/${enc(agent)}/install`, {
    method: "POST",
    headers: headers(),
  });
  await checkOk(r);
  return (await r.json()) as DeliveryStatusOut;
}

export async function removeDelivery(agent: string): Promise<DeliveryStatusOut> {
  const r = await fetch(`${memoryRoot()}/delivery/${enc(agent)}`, {
    method: "DELETE",
    headers: headers(),
  });
  await checkOk(r);
  return (await r.json()) as DeliveryStatusOut;
}
