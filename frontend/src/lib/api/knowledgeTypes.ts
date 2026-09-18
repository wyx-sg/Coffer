// frontend/src/lib/api/knowledgeTypes.ts
//
// Wire types for the `knowledge` kind. A collection is a top-level folder under
// the knowledge root holding exactly TWO lanes (ADR knowledge-is-plain-files):
// `sources/`, what the person and the agents wrote, and `topics/`, what
// Coffer's curation derived from it. The lane is part of every path
// (`shopee/sources/gw.md`, `shopee/topics/account-gateway.md`), which is why
// nothing here carries a separate lane field.
//
// Every `path` here is RELATIVE to the knowledge root. The two ABSOLUTE paths —
// `file_path` and `folder_path` on a read — exist only so the viewer can hand
// them to the OS file actions (FR-041).
//
// These are the knowledge contract's generated schemas
// (`specs/knowledge/contracts/api.openapi.yaml` → `generated/knowledge.ts`)
// under the names the hooks and pages already import.
//
// There is no search or grep type in this file because the layer exposes no
// retrieval at all (FR-033): an agent reads the files with its own tools at the
// paths its delivered skill carries, and the filter box over a lane is
// client-side and name-only (`lib/knowledge/filter.ts`).
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
  /** The collection Resource's immutable identity — what `curate` takes, and
   *  what a link to this collection is built from. */
  uid: string;
  /** A mutable label, and the collection's directory name under the knowledge
   *  root. Display it, and build the `path` / `collection` arguments of the
   *  FILE routes from it: those address a place on disk. */
  name: string;
  description: string | null;
  /** Files under `sources/`, counted recursively. */
  source_count: number;
  /** Documents under `topics/`, counted recursively. */
  topic_count: number;
}

export interface CollectionListOut {
  collections: CollectionOut[];
}

/** One level of one lane — the tree descends a level per request. */
export type TreeOut = Schemas["TreeOut"];

/**
 * What one curation pass did. `status` is what the page reports: every one of
 * them is a 200, because a vault with no internal model configured, or with
 * nothing pending, is an ordinary state rather than a failed request (FR-029).
 */
export type CurationOut = Schemas["CurationOut"];

/** What one successful `POST /knowledge/upload` produced. */
export type IngestedDocumentOut = Schemas["IngestedDocumentOut"];
