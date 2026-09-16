// frontend/src/lib/api/memoryTypes.ts
//
// Wire types for the `memory` kind. Memory is Coffer's own distillation of the
// agents' native memories — it reads them, never writes them, and what it
// writes instead is a folder per repository holding `MEMORY.md` (the index),
// `notes/` (Coffer's own notes, one topic per file), `RETIRED.md` (what left
// and why) and a hidden `.raw/` of the verbatim entries it read. See
// specs/memory/spec.md and
// docs/decisions/aggregate-agent-memory-never-write-it.md.
//
// The UI writes none of it: a partition is shown as what it literally is on
// disk, a folder under `~/.coffer/memory/`, so the file types below carry no
// fingerprint and there is no write shape to send.
//
// These are hand-written rather than generated: `specs/memory`'s contract
// names the file shapes `FileNodeOut` / `FileTreeOut` / `FileContentOut`,
// while every consumer here imports the `Memory…`-prefixed names below, so the
// memory contract is deliberately absent from `CONTRACTS` in
// `scripts/codegen.mjs` until that rename is made. Field names match
// `backend/coffer/surfaces/http/memory/schemas.py` exactly.

/** One partition: a repository's slug, or `global` for notes about the person.
 *
 *  Keyed on a REPOSITORY, not a working directory — a worktree and a second
 *  clone of the same repo resolve to one partition (FR-014). */
export interface PartitionOut {
  name: string;
  /** Absolute path of the repository's main working tree; empty for `global`. */
  repository_path: string;
  /** What the repository was resolved to: `remote:<host>/<path>` when it has an
   *  `origin`, `path:<abs>` when it has none. Empty for `global`. */
  repository_key: string;
  note_count: number;
  /** True when `repository_path` is no longer on disk. Surfaced rather than
   *  hidden: such a partition is delivered to nobody, and only the developer
   *  can decide to delete it (FR-016). */
  unresolvable: boolean;
}

export interface PartitionListOut {
  partitions: PartitionOut[];
}

/** One entry in a partition's own directory — the same node shape the skill
 *  file tree reads, because it is the same kind of thing: a folder on disk. */
export interface MemoryFileNode {
  name: string;
  /** POSIX path relative to the partition directory; `""` for the root. */
  path: string;
  /** Absolute on-disk path of this node (file viewers hand it to FileActions). */
  abs_path?: string;
  /** Absolute on-disk path of the containing folder. */
  folder_abs_path?: string;
  type: "file" | "dir";
  /** True for `.raw/` and everything under it: the verbatim entries
   *  aggregation read out of the agents, not Coffer's own writing. The server
   *  decides — the path convention is only a fallback for a node that predates
   *  the field. */
  derived: boolean;
  size: number | null;
  /** True on a dir whose children were clipped at the max tree depth. */
  truncated: boolean;
  children: MemoryFileNode[] | null;
}

export interface MemoryFileTreeOut {
  root: MemoryFileNode;
}

/** One memory file's content. Read-only — no fingerprint, because nothing
 *  here conditions a write. */
export interface MemoryFileContentOut {
  path: string;
  /** Absolute on-disk path of the file (handed to FileActions). */
  abs_path?: string;
  /** Absolute on-disk path of the file's containing folder. */
  folder_abs_path?: string;
  content: string;
  truncated: boolean;
  binary: boolean;
  size: number;
}

export interface AggregationResultOut {
  partitions: string[];
  /** Verbatim entries written under the partitions' `.raw/` this pass. */
  entries_written: number;
  sources_read: number;
  sources_skipped: number;
  /** Native source paths that failed to parse (FR-005) — the other agent's
   *  aggregation still completed. */
  failures: string[];
}

/** What one distil pass did to a partition: the four actions its routing stage
 *  is confined to. A note it rewrote is `merged`, a note it wrote fresh is
 *  `opened`, a note it took out of `notes/` and recorded in `RETIRED.md` is
 *  `retired`, and an entry it judged not worth a note is `dropped`. */
export interface DistilResultOut {
  partition: string;
  merged: number;
  opened: number;
  retired: number;
  dropped: number;
  model_used: boolean;
}

/** Per-agent delivery state — whether Coffer's hook is written into that
 *  agent's settings. Whether it has fired is read from the audit log, one
 *  entry per fire (FR-022), not from here. */
export interface DeliveryStatusOut {
  agent: string;
  installed: boolean;
  /** Coffer's own CLI invocation the hook runs. */
  command: string;
  /** The hook event delivery is attached to (e.g. `SessionStart`). */
  event: string;
}

export interface DeliveryStatusListOut {
  delivery: DeliveryStatusOut[];
}
