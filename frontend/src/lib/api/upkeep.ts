// frontend/src/lib/api/upkeep.ts
//
// The one read for "what is this daemon rewriting right now" (`/api/v1/upkeep/
// runs`, contract `specs/resource-framework`).
//
// An *upkeep pass* is one of the long, model-driven rewrites the vault does to
// itself: memory's organise over a partition, knowledge's tidy over a
// collection. Both run for minutes and both can be started from a button, the
// CLI or a timer — so a button that remembers "I am running" only in its own
// component state forgets on the next navigation, and the second click starts
// a second pass. This is where that state actually lives.
//
// One endpoint answers for every kind, so a page filters the list for its own
// target rather than each kind carrying a near-identical per-target route.
//
// Transport via the shared `call` (.agents/frontend.md §4); wire types are the
// generated ones.

import { call } from "@/lib/api/call";
import type { components } from "@/lib/api/generated/resource-framework";

export type UpkeepRunOut = components["schemas"]["UpkeepRunOut"];
export type UpkeepRunListOut = components["schemas"]["UpkeepRunListOut"];

/** The two kinds that have an upkeep pass. Matches the backend's own resource
 *  kind names, which is what `UpkeepRunOut.kind` carries. */
export type UpkeepKind = "memory" | "knowledge";

/** Every pass in flight, oldest first. An empty list means nothing is
 *  running — a target absent from it has no pass. */
export function listUpkeepRuns(): Promise<UpkeepRunListOut> {
  return call<UpkeepRunListOut>("/upkeep/runs");
}
