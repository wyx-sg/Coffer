// frontend/src/lib/api/knowledgeTypes.ts
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
// The catalogue, file and tidy shapes are the knowledge contract's generated
// schemas (`specs/knowledge/contracts/api.openapi.yaml` → `generated/knowledge.ts`)
// under the names the hooks and pages already import. Search and upload stay
// hand-written: the contract exposes `/knowledge/grep` (a flat match list)
// where the daemon serves `/knowledge/search` (hits grouped per file), and has
// no `/knowledge/upload` route at all.
import type { components } from "@/lib/api/generated/knowledge";

type Schemas = components["schemas"];

/** One file's frontmatter + body, plus the absolute paths for file actions. */
export type FileOut = Schemas["FileOut"];

/**
 * Who wrote a file, from its frontmatter. Mirrors the backend
 * `coffer.domain.knowledge.Actor`. This is the authorship vocabulary —
 * distinct from the broader audit-log actor vocabulary (request origins
 * `ui`/`cli`/`api` plus the domain actors) rendered via `audit.actor.*`.
 */
export type KnowledgeActor = FileOut["actor"];

/**
 * One collection: a top-level folder, described by its own `README.md`.
 *
 * Hand-written rather than the contract's `CollectionOut`: the UI (and its
 * fixtures) model a collection with no README as `description: null`, which
 * the contract types as `string` only.
 */
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
export type TreeDirectoryOut = Schemas["DirectoryOut"];

/** A Markdown file at the listed level, with its frontmatter metadata. */
export type TreeFileOut = Schemas["FileSummaryOut"];

/** One level of the catalogue — the tree descends a level per request (FR-021). */
export type TreeOut = Schemas["TreeOut"];

/**
 * Result of a manual tidy pass. Only `status` is consumed by the UI (the pass
 * reports its own numbers to Coffer's audit log).
 */
export type TidyOut = Schemas["TidyOut"];

/** What one successful `POST /knowledge/upload` produced. */
export interface IngestedDocumentOut {
  /** Path of the converted Markdown file, relative to the knowledge root. */
  path: string;
  title: string;
  description: string;
  /** Which converter produced this file. */
  converter: string;
  /** Absolute path of the kept original, under the collection's hidden `.raw/`. */
  raw_path: string;
}
