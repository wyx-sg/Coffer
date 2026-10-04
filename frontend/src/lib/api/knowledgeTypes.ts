// frontend/src/lib/api/knowledgeTypes.ts
//
// Wire types for the `knowledge` kind. A collection is a top-level folder under
// the knowledge root holding ONE tree of Markdown documents that people and
// curation write together (`shopee/account-gateway.md`,
// `shopee/apis/login.md`). New material waits in a hidden inbox until a
// curation pass curates it into those documents. The tree lists that inbox as a
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
 *  to be curated (readable, never saved or deleted). */
export type FileOut = Schemas["FileOut"];

/** A document's new body from the web UI's editor; the frontmatter stays as
 *  it is on disk, so none of it is sent. */
export type FileSave = Schemas["FileSave"];

/** One collection: a top-level folder, described by its own `README.md`. It
 *  has no title — it is shown by its folder name. */
export type CollectionOut = Schemas["CollectionOut"];

export type CollectionListOut = Schemas["CollectionListOut"];

/** One level of a collection's tree — it descends a level per request. */
export type TreeOut = Schemas["TreeOut"];

/**
 * What Curate now did: every pass it ran, in order — one per pending item
 * until none was left, stopping at the first failed pass (see "Run curation on
 * a sweep and on demand"). `total` is how many items were pending when it
 * started. Every status is a 200: no model, or nothing pending, is an ordinary
 * state rather than a failed request.
 */
export type CurationRunOut = Schemas["CurationRunOut"];

/**
 * What one successful `POST /knowledge/upload` produced: either a document
 * (`path`, when there is no internal model to curate it and it was promoted on
 * the spot) or material waiting in the inbox (`pending`, `path` null).
 */
export type IngestedDocumentOut = Schemas["IngestedDocumentOut"];

/** One change to knowledge: one commit in the vault's history, naming its
 *  writer (see "Keep every document's history and undo a pass as a whole"). */
export type ChangeOut = Schemas["ChangeOut"];

/** The recent-changes timeline, newest first, with the items still waiting. */
export type ChangesOut = Schemas["ChangesOut"];

/** One change in full: every document it touched, each with its diff. */
export type ChangeDetailOut = Schemas["ChangeDetailOut"];

export type DocumentDiffOut = Schemas["DocumentDiffOut"];

export type WaitingItemOut = Schemas["WaitingItemOut"];

/** A document's versions, newest first. */
export type DocumentHistoryOut = Schemas["DocumentHistoryOut"];

export type DocumentVersionOut = Schemas["DocumentVersionOut"];

/** What one version did to a document, as a unified diff. */
export type VersionDiffOut = Schemas["VersionDiffOut"];

/** A document's body as one version left it. */
export type VersionBodyOut = Schemas["VersionBodyOut"];
