// frontend/src/lib/api/memoryTypes.ts
//
// Wire types for the `memory` kind. Memory is Coffer's read-only aggregation
// of the agents' own native memories, normalised into files partitioned by
// project (plus `global`) — see docs/decisions/aggregate-agent-memory-never-write-it.md
// and specs/memory/spec.md. Coffer never writes an agent's native memory, and
// the UI no longer writes Coffer's own copy either: a partition is shown as
// what it literally is on disk, a folder under `~/.coffer/memory/`, so the
// file types below carry no fingerprint and there is no write shape to send.
//
// There is no memory OpenAPI contract under `specs/*/contracts/` for
// `npm run codegen` to read, so these are hand-written. Field names match
// `backend/coffer/surfaces/http/memory/schemas.py` exactly.

/** One partition: a project's slug, or `global` for facts about the person. */
export interface PartitionOut {
  name: string;
  /** Absolute project root this partition was named from; empty for `global`. */
  project_root: string;
  fact_count: number;
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
  facts_written: number;
  sources_read: number;
  sources_skipped: number;
  /** Native source paths that failed to parse (FR-005) — the other agent's
   *  aggregation still completed. */
  failures: string[];
}

export interface OrganiseResultOut {
  partition: string;
  merged: number;
  superseded: number;
  conflicts: number;
  model_used: boolean;
}

/** Per-agent delivery state — whether Coffer's hook is written into that
 *  agent's settings. Whether it has fired is read from the audit log, one
 *  entry per fire (FR-055), not from here. */
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
