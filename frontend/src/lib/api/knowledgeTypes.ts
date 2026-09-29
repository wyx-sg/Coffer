// frontend/src/lib/api/knowledgeTypes.ts
//
// Wire types for the `knowledge` kind. A collection is a top-level folder under
// the knowledge root holding ONE tree of Markdown documents that people and
// curation write together (`shopee/account-gateway.md`,
// `shopee/apis/login.md`). New material waits in a hidden inbox until a
// curation pass merges it into those documents. The tree lists that inbox as a
// `.inbox` folder at the collection root and every row and read inside it
// carries `inbox: true` — material a person may read but not edit or delete.
//
// Every `path` here is RELATIVE to the knowledge root. The two ABSOLUTE paths —
// `file_path` and `folder_path` on a read — exist only so the viewer can hand
// them to the OS file actions (see "Return absolute paths on reads").
//
// These are the knowledge contract's generated schemas
// (`openspec/specs/knowledge/contracts/api.openapi.yaml` → `generated/knowledge.ts`)
// under the names the hooks and pages already import.
//
// There is no search or grep type in this file because the layer exposes no
// retrieval at all (see "Expose exactly one knowledge tool"): an agent reads the files with its own
// tools at the paths its delivered skill carries, and a person reads them
// through the collection's tree.
import type { components } from "@/lib/api/generated/knowledge";

type Schemas = components["schemas"];

/** One file's frontmatter + body, plus the absolute paths for file actions,
 *  the `fingerprint` a save hands back, and `inbox` for an item still waiting
 *  to be merged (readable, never saved or deleted). */
export type FileOut = Schemas["FileOut"];

/** A document's new body from the web UI's editor; the frontmatter stays as
 *  it is on disk, so none of it is sent. */
export type FileSave = Schemas["FileSave"];

/**
 * One collection: a top-level folder, described by its own `README.md`.
 *
 * Hand-written rather than the contract's `CollectionOut`: the UI (and its
 * fixtures) model a collection with no README as `description: null`, which
 * the contract types as `string` only.
 */
export interface CollectionOut {
  /** The collection Resource's immutable identity — what `curate` takes, and
   *  what a link to this collection is built from. */
  uid: string;
  /** A mutable label, and the collection's directory name under the knowledge
   *  root. Display it, and build the `path` / `collection` arguments of the
   *  FILE routes from it: those address a place on disk. */
  name: string;
  /** The display title a person chose, shown in place of the name; null when
   *  none is set. Edited through `PATCH /resources/{uid}`. */
  title?: string | null;
  description: string | null;
  /** Documents an agent can read today, counted recursively. */
  document_count: number;
  /** Material still waiting in the inbox to be merged into those documents —
   *  counted apart because it is exactly what an agent cannot see yet. */
  pending_count: number;
}

export interface CollectionListOut {
  collections: CollectionOut[];
}

/** One level of a collection's tree — it descends a level per request. */
export type TreeOut = Schemas["TreeOut"];

/**
 * What one curation pass did. `status` is what the page reports: every one of
 * them is a 200, because a vault with no internal model configured, or with
 * nothing pending, is an ordinary state rather than a failed request (see
 * "Promote material directly when no model is configured").
 */
export type CurationOut = Schemas["CurationOut"];

/**
 * What one successful `POST /knowledge/upload` produced: either a document
 * (`path`, when there is no internal model to merge it and it was promoted on
 * the spot) or material waiting in the inbox (`pending`, `path` null).
 */
export type IngestedDocumentOut = Schemas["IngestedDocumentOut"];
