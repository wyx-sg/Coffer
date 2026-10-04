// frontend/src/lib/api/memoryTypes.ts
//
// Wire types for the `memory` kind, every one an alias of the generated
// contract (`generated/memory.ts`, from `openspec/specs/memory`'s
// `api.openapi.yaml`, itself generated from
// `backend/coffer/surfaces/http/memory/*.py`). Memory is Coffer's own
// distillation of the agents' native memories — it reads them, never writes
// them. The one write shape is a person's edit of a memory's body (NoteSave).
//
// The web UI calls a note a "memory" (中文 记忆条目, spec memory "Present a
// partition as its memories"); the wire and the disk keep the word note.
import type { components as MemoryWire } from "@/lib/api/generated/memory";

type Schemas = MemoryWire["schemas"];

/** One partition: a repository's slug, or `global` for memories about the
 *  person. Keyed on a REPOSITORY, not a working directory (see "Identify a
 *  partition by its repository"). */
export type PartitionOut = Schemas["PartitionOut"];
export type PartitionListOut = Schemas["PartitionListOut"];

/** One memory in a partition's list — no body, no provenance. */
export type NoteSummaryOut = Schemas["NoteSummaryOut"];
export type NoteListOut = Schemas["NoteListOut"];

/** One memory in full: its body (never its frontmatter) and its provenance. */
export type NoteOut = Schemas["NoteOut"];

/** A memory's new body from the editor, with the fingerprint it was read at. */
export type NoteSave = Schemas["NoteSave"];
export type OriginOut = Schemas["OriginOut"];

/** A retired memory and the reason it left. */
export type RetiredNoteOut = Schemas["RetiredNoteOut"];
export type RetiredListOut = Schemas["RetiredListOut"];

/** The exact session-start text each agent receives in a partition's project. */
export type DeliveredOut = Schemas["DeliveredOut"];

/** Per agent, the last seven days of memory delivery. */

export type MemoryFileTreeOut = Schemas["FileTreeOut"];

export type AggregationResultOut = Schemas["AggregationResultOut"];

/** When Coffer last read the agents' memory, and whose it could not read. */
export type ReadingOut = Schemas["ReadingOut"];
