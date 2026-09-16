// frontend/src/lib/api/knowledgeTypes.ts
//
// Wire types for the `knowledge` kind. Knowledge is a directory of Markdown
// files, not an index (ADR knowledge-is-plain-files): a COLLECTION is a
// top-level folder under the knowledge root and the only boundary the system
// knows, and everything below it is the user's own filing.
//
// Every `path` here is RELATIVE to the knowledge root (`shopee/account/gw.md`).
// The two ABSOLUTE paths — `file_path` and `folder_path` on a read — exist only
// so the viewer can hand them to the OS file actions (FR-036).
//
// The catalogue, file and tidy shapes are the knowledge contract's generated
// schemas (`specs/knowledge/contracts/api.openapi.yaml` → `generated/knowledge.ts`)
// under the names the hooks and pages already import. Upload's shapes are the
// exception and stay hand-written here.
//
// There is no search type in this file because there is no search in the UI:
// the filter box over a collection is client-side and name-only
// (`lib/knowledge/filter.ts`), and retrieval over file BODIES is the agents'
// surface (`coffer__search`) and the CLI's. `/knowledge/search` being in the
// contract is therefore not a shape this frontend is missing.
import type { components } from "@/lib/api/generated/knowledge";

type Schemas = components["schemas"];

/** One file's frontmatter + body, plus the absolute paths for file actions. */
export type FileOut = Schemas["FileOut"];

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

/** A Markdown file at the listed level, with its frontmatter metadata. */

/** One level of the catalogue — the tree descends a level per request (FR-013). */
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
