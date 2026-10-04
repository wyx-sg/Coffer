// frontend/src/lib/api/memory.ts
//
// Request helpers for the `memory` kind's REST family (`/api/v1/memory/*`,
// spec memory "Manage memory in the web UI"). Partition
// deletion is deliberately absent: a partition is one `memory` Resource, so it
// goes through the kind-agnostic `DELETE /api/v1/resources/{uid}`.
//
// A partition is addressed by its uid. The delivery hook is not managed here:
// it is one part of an agent's Coffer connection (`agentsApi.connect`).
//
// Transport via the typed client (.agents/frontend.md §4); wire types in
// `memoryTypes.ts`, aliases of the generated contract.

import { getApiClient, unwrap, unwrapVoid } from "@/lib/api/client";
import type {
  AggregationResultOut,
  DeliveredOut,
  MemoryFileTreeOut,
  NoteListOut,
  NoteOut,
  NoteSave,
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

/** Save a memory's body ("Edit a memory in the web UI or on disk"): the
 *  frontmatter is kept. `expected_fingerprint` is the one the read carried; a
 *  note changed since is refused with 409 `MEMORY_NOTE_CONFLICT`, whose
 *  `details` carry the note's current body and fingerprint. Resolves with the
 *  note as saved, new fingerprint included. */
export function saveNote(uid: string, slug: string, payload: NoteSave): Promise<NoteOut> {
  return unwrap(
    getApiClient().PUT("/memory/partitions/{uid}/notes/{slug}", {
      params: { path: { uid, slug } },
      body: payload,
    }),
  );
}

/** Delete a memory by hand: the file leaves `notes/` and a "Deleted by hand"
 *  record goes into RETIRED.md carrying its entry ids, so the next update does
 *  not bring it back. 404 for an unknown slug. */
export function deleteNote(uid: string, slug: string): Promise<void> {
  return unwrapVoid(
    getApiClient().DELETE("/memory/partitions/{uid}/notes/{slug}", {
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
