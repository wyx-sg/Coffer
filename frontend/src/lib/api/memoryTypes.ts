// frontend/src/lib/api/memoryTypes.ts
//
// Wire types for the `memory` kind. Memory is Coffer's own distillation of the
// agents' native memories — it reads them, never writes them, and what it
// writes instead is a folder per repository holding `MEMORY.md` (the index),
// `notes/` (Coffer's own notes, one topic per file), `RETIRED.md` (what left
// and why) and a hidden `.raw/` of the verbatim entries it read. See
// openspec/specs/memory/spec.md and
// docs/decisions/aggregate-agent-memory-never-write-it.md.
//
// The UI writes none of it: a partition is shown as what it literally is on
// disk, a folder under `~/.coffer/memory/`, so the file types below carry no
// fingerprint and there is no write shape to send.
//
// These are hand-written rather than generated: `openspec/specs/memory`'s contract
// names the file shapes `FileNodeOut` / `FileTreeOut` / `FileContentOut`,
// while every consumer here imports the `Memory…`-prefixed names below, so the
// memory contract is deliberately absent from `CONTRACTS` in
// `scripts/codegen.mjs` until that rename is made. Field names match
// `backend/coffer/surfaces/http/memory/schemas.py` exactly.

import type { components as MemoryWire } from "@/lib/api/generated/memory";
/** One partition: a repository's slug, or `global` for notes about the person.
 *
 *  Keyed on a REPOSITORY, not a working directory — a worktree and a second
 *  clone of the same repo resolve to one partition (see "Identify a
 *  partition by its repository"). */
export type PartitionOut = MemoryWire["schemas"]["PartitionOut"];

export type PartitionListOut = MemoryWire["schemas"]["PartitionListOut"];

/** One entry in a partition's own directory — the same node shape the skill
 *  file tree reads, because it is the same kind of thing: a folder on disk. */
export type MemoryFileNode = MemoryWire["schemas"]["FileNodeOut"];

export type MemoryFileTreeOut = MemoryWire["schemas"]["FileTreeOut"];

/** One memory file's content. Read-only — no fingerprint, because nothing
 *  here conditions a write. */
export type MemoryFileContentOut = MemoryWire["schemas"]["FileContentOut"];

export type AggregationResultOut = MemoryWire["schemas"]["AggregationResultOut"];
