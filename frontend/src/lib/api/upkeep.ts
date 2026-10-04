// frontend/src/lib/api/upkeep.ts
//
// The one read for "what is this daemon rewriting right now" (`/api/v1/upkeep/
// runs`, contract `openspec/specs/resource-framework`).
//
// An *upkeep pass* is a long rewrite the vault does to itself: memory's update
// (aggregate, then distil). It can be started from a button, the CLI or a
// timer — so a button that remembers "I am running" only in its own component
// state forgets on the next navigation, and the second click starts a second
// pass. This is where that state actually lives.
//
// One endpoint answers for every pass, so a page filters the list for its own
// target rather than carrying a near-identical per-target route.
//
// Transport via the typed client (.agents/frontend.md §4); wire types are the
// generated ones.

import { getApiClient, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/generated/resource-framework";

export type UpkeepRunOut = components["schemas"]["UpkeepRunOut"];
export type UpkeepRunListOut = components["schemas"]["UpkeepRunListOut"];

/** The kinds that have an upkeep pass. Matches the backend's own resource
 *  kind names, which is what `UpkeepRunOut.kind` carries. */
export type UpkeepKind = "memory";

/** Every pass in flight, oldest first. An empty list means nothing is
 *  running — a target absent from it has no pass. */
export function listUpkeepRuns(): Promise<UpkeepRunListOut> {
  return unwrap(getApiClient().GET("/upkeep/runs"));
}
