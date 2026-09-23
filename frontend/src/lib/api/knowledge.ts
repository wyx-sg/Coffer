// frontend/src/lib/api/knowledge.ts
//
// Request helpers for the `knowledge` kind. Nothing here retrieves and nothing
// here reads an index: a collection is one folder of Markdown documents walked
// a level at a time, frontmatter read at call time (ADR
// knowledge-is-plain-files), so a document someone edited in their own editor
// is what the very next call returns and there is nothing to reindex.
//
// There is no `search` and no `grep` here because the daemon serves neither
// (see "Cover collection management on REST and the CLI"). New knowledge goes in as MATERIAL — an
// upload here, an agent's `coffer__write`, the CLI — which waits in the collection's hidden inbox
// until a curation pass merges it into the documents; with no internal model
// configured it becomes a document as it is.
//
// Deleting a COLLECTION is deliberately absent: a collection is one `knowledge`
// Resource, so it goes through the kind-agnostic `DELETE /resources/{uid}`
// (`useDeleteResource`) like every other kind. Only files are deleted here.
//
// Two vocabularies meet in this module and both are correct. `curate` addresses
// a collection, so it takes the collection's `uid`. The file routes address a
// place on disk, and a collection's directory is named after it, so `path` and
// `collection` are NAMES — the same strings the tree hands back. A caller that
// holds a `CollectionOut` has both and picks by what it is asking for.
//
// Transport via the shared `call` (.agents/frontend.md §4); wire types in
// `knowledgeTypes.ts`.

import { call, enc } from "@/lib/api/call";
import type {
  CollectionListOut,
  CollectionOut,
  CurationOut,
  FileOut,
  IngestedDocumentOut,
  TreeOut,
} from "./knowledgeTypes";

// Re-export the wire types so `import { … } from "./api"` sees one surface.
export * from "./knowledgeTypes";

/** `/api/v1/knowledge` — the root every knowledge route hangs off. */
const ROOT = "/knowledge";

// --- collections ------------------------------------------------------------

export function listCollections(): Promise<CollectionListOut> {
  return call<CollectionListOut>(`${ROOT}/collections`);
}

/**
 * Create a collection — one top-level folder, and one `knowledge` Resource so
 * per-agent scope can authorize it. The description lands in the folder's
 * `README.md`, which is where the catalogue reads it back from.
 */
export function createCollection(payload: {
  name: string;
  description?: string | null;
}): Promise<CollectionOut> {
  return call<CollectionOut>(`${ROOT}/collections`, { method: "POST", body: payload });
}

// --- catalogue --------------------------------------------------------------

/**
 * List ONE level of a collection: the immediate subdirectories and documents
 * under `path`, relative to the knowledge root — `shopee` for the collection
 * itself, `shopee/account` for a folder inside it. The tree descends a level
 * per request. The collection's own `README.md` and the hidden inbox never
 * appear: neither is a document.
 */
export function getTree(path: string): Promise<TreeOut> {
  return call<TreeOut>(`${ROOT}/tree?path=${enc(path)}`);
}

export function getFile(path: string): Promise<FileOut> {
  return call<FileOut>(`${ROOT}/file?path=${enc(path)}`);
}

/**
 * Remove ONE document — any of them: the collection is the person's as much
 * as curation's (see "Let only a person delete a document"). `path` is relative to the knowledge
 * root, the same string the tree and `getFile` use, and the daemon refuses anything that
 * escapes it.
 *
 * A document is the only copy: there is no index to fall out of step and
 * nothing to restore it from but the sync remote's history, which is why every
 * caller confirms first. 204, so nothing comes back.
 */
export function deleteFile(path: string): Promise<void> {
  return call<void>(`${ROOT}/file?path=${enc(path)}`, { method: "DELETE" });
}

// --- curation ---------------------------------------------------------------

/**
 * Run ONE curation pass over one collection now — the manual trigger for the
 * pass the background sweep otherwise runs on an interval. It takes one
 * pending item and merges it into the collection's documents.
 *
 * `document` names a particular document to carry through; omitted, the pass
 * takes the oldest pending item — inbox material first, then a document edited
 * since curation last saw it — which is what the page's button wants. A pass
 * with no internal model configured comes back `no_model`, having promoted the
 * inbox to documents as it stood (`promoted`) — a clean 200, not an error — so
 * every status here is something the page reports rather than a failure.
 *
 * A second pass over the same collection is refused with 409
 * `UPKEEP_ALREADY_RUNNING` rather than queued (see "Run one pass per collection
 * at a time").
 */
export function curateCollection(uid: string, document?: string | null): Promise<CurationOut> {
  return call<CurationOut>(`${ROOT}/collections/${enc(uid)}/curate`, {
    method: "POST",
    body: { document: document ?? null },
  });
}

// --- ingestion ----------------------------------------------------------------

/**
 * Convert an uploaded document into material for a collection. The Markdown
 * extracted from it joins the collection's inbox and is merged into the
 * documents by the next pass (`pending: true`); with no internal model
 * configured it is promoted to a document on the spot and `path` names it.
 * Neither the original nor the extracted Markdown is kept beyond that — the
 * documents are what the collection holds.
 */
export function uploadFile(params: {
  /** The collection's NAME: this lands material in its directory. */
  collection: string;
  file: File;
}): Promise<IngestedDocumentOut> {
  const form = new FormData();
  form.append("file", params.file);
  form.append("collection", params.collection);
  // A FormData body goes out with no Content-Type: the browser sets the
  // multipart boundary itself (see `call`).
  return call<IngestedDocumentOut>(`${ROOT}/upload`, { method: "POST", body: form });
}
