// frontend/src/kinds/knowledge/types.ts
//
// Wire types for the `knowledge` kind. Knowledge is a directory of Markdown
// files, not an index (ADR knowledge-is-plain-files): a COLLECTION is a
// top-level folder under the knowledge root and the only boundary the system
// knows, and everything below it is the user's own filing.
//
// Every `path` here is RELATIVE to the knowledge root (`shopee/account/gw.md`).
// The two ABSOLUTE paths — `file_path` and `folder_path` on a read — exist only
// so the viewer can hand them to the OS file actions (FR-062).
//
// The knowledge routes are not in the mcp-gateway OpenAPI contract that
// `npm run codegen` reads, so these are hand-written like the sibling kinds'.

/**
 * Who wrote a file, from its frontmatter. Mirrors the backend
 * `coffer.domain.knowledge.Actor`. This is the authorship vocabulary —
 * distinct from the broader audit-log actor vocabulary (request origins
 * `ui`/`cli`/`api` plus the domain actors) rendered via `audit.actor.*`.
 */
export type KnowledgeActor = "agent" | "user";

/** One collection: a top-level folder, described by its own `README.md`. */
export interface CollectionOut {
  name: string;
  description: string | null;
  /** Markdown files anywhere beneath it, hidden directories excluded. */
  file_count: number;
}

export interface CollectionListOut {
  collections: CollectionOut[];
}

/** An immediate subdirectory of the listed level. */
export interface TreeDirectoryOut {
  /** Path relative to the knowledge root, e.g. `shopee/account`. */
  path: string;
  name: string;
  file_count: number;
}

/** A Markdown file at the listed level, with its frontmatter metadata. */
export interface TreeFileOut {
  /** Path relative to the knowledge root, e.g. `shopee/account/gw.md`. */
  path: string;
  title: string;
  description: string | null;
  actor: KnowledgeActor;
  updated_at: string;
}

/** One level of the catalogue — the tree descends a level per request (FR-021). */
export interface TreeOut {
  path: string;
  directories: TreeDirectoryOut[];
  files: TreeFileOut[];
}

/** One file's frontmatter + body, plus the absolute paths for file actions. */
export interface FileOut {
  path: string;
  title: string;
  description: string | null;
  actor: KnowledgeActor;
  created_at: string;
  updated_at: string;
  /** Markdown body with the frontmatter block stripped. */
  body: string;
  /** Absolute on-disk path of the file itself (FileActions). */
  file_path: string;
  /** Absolute on-disk path of its containing folder (FileActions). */
  folder_path: string;
}

/**
 * Result of a manual tidy pass. Only `status` is consumed by the UI (the pass
 * reports its own numbers to Coffer's audit log), so the shape stays open to
 * whatever counters the backend adds.
 */
export interface TidyOut {
  status: string;
}
