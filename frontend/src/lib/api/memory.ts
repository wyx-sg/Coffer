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
// Transport via the typed client (.agents/frontend.md §4); wire types in
// `memoryTypes.ts`, aliases of the generated contract.

import { getApiClient, unwrap } from "@/lib/api/client";
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

const partition = (uid: string) => ({ params: { path: { uid } } });

// --- partitions -------------------------------------------------------------

export function listPartitions(): Promise<PartitionListOut> {
  return unwrap(getApiClient().GET("/memory/partitions"));
}

// --- update (aggregation, then distil) ---------------------------------------

/** Update memory now (spec memory "Update memory in one action"): read every
 * registered agent's native memory, then distil every partition that gained
 * raw entries. */
export function sync(): Promise<AggregationResultOut> {
  return unwrap(getApiClient().POST("/memory/sync"));
}

// --- one partition's memories ("Present a partition as its memories") -------

export function listNotes(uid: string): Promise<NoteListOut> {
  return unwrap(getApiClient().GET("/memory/partitions/{uid}/notes", partition(uid)));
}

export function getNote(uid: string, slug: string): Promise<NoteOut> {
  return unwrap(
    getApiClient().GET("/memory/partitions/{uid}/notes/{slug}", {
      params: { path: { uid, slug } },
    }),
  );
}

export function listRetired(uid: string): Promise<RetiredListOut> {
  return unwrap(getApiClient().GET("/memory/partitions/{uid}/retired", partition(uid)));
}

/** The partition directory — read only for the absolute paths that open-in-
 *  editor and reveal need. */
export function listPartitionFiles(uid: string): Promise<MemoryFileTreeOut> {
  return unwrap(getApiClient().GET("/memory/partitions/{uid}/files", partition(uid)));
}

// --- delivery (web-ui "Show memory delivery on the Memory page") -------------

/** The exact session-start text each connected agent receives in the
 *  partition's project. */
export function getDelivered(uid: string): Promise<DeliveredOut> {
  return unwrap(getApiClient().GET("/memory/partitions/{uid}/delivered", partition(uid)));
}

/** When the agents' memory was last read, and which agents failed. */
export function getReading(): Promise<ReadingOut> {
  return unwrap(getApiClient().GET("/memory/reading"));
}

/** Per agent, deliveries, memories read and the last delivery over the last
 *  seven days. */
export function getDeliveries(): Promise<DeliveryOverviewOut> {
  return unwrap(getApiClient().GET("/memory/deliveries"));
}
