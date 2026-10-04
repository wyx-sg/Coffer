// frontend/src/lib/api/knowledge.ts
//
// Request helpers for the `knowledge` kind. Nothing here retrieves and nothing
// here reads an index: a collection is one folder of Markdown documents walked
// a level at a time, frontmatter read at call time (ADR
// knowledge-is-plain-files), so a document someone edited in their own editor
// is what the very next call returns and there is nothing to reindex.
//
// There is no `search` and no `grep` here because the daemon serves neither
// (see "Cover knowledge management on REST and the CLI"). New knowledge goes in as MATERIAL — an
// upload here, an agent's file in `.inbox/` — which waits in the collection's hidden inbox
// until a curation pass curates it into the documents; with no internal model
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
// Transport via the typed client (.agents/frontend.md §4); wire types in
// `knowledgeTypes.ts`.

import { getApiClient, unwrap, unwrapVoid } from "@/lib/api/client";
import type {
  ChangeDetailOut,
  ChangeOut,
  ChangesOut,
  CollectionListOut,
  CollectionOut,
  CurationRunOut,
  DocumentHistoryOut,
  FileOut,
  FileSave,
  IngestedDocumentOut,
  VersionBodyOut,
  TreeOut,
  VersionDiffOut,
} from "./knowledgeTypes";

// Re-export the wire types so `import { … } from "./api"` sees one surface.
export * from "./knowledgeTypes";

// --- collections ------------------------------------------------------------

export function listCollections(): Promise<CollectionListOut> {
  return unwrap(getApiClient().GET("/knowledge/collections"));
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
  return unwrap(getApiClient().POST("/knowledge/collections", { body: payload }));
}

// --- catalogue --------------------------------------------------------------

/**
 * List ONE level of a collection: the immediate subdirectories and documents
 * under `path`, relative to the knowledge root — `shopee` for the collection
 * itself, `shopee/account` for a folder inside it. The tree descends a level
 * per request. The collection's own `README.md` never appears. A non-empty
 * inbox is listed first at the collection root as a directory with
 * `inbox: true`, and `<collection>/.inbox` lists its items (see "Hide
 * dot-prefixed entries except the inbox").
 */
export function getTree(path: string): Promise<TreeOut> {
  return unwrap(getApiClient().GET("/knowledge/tree", { params: { query: { path } } }));
}

/** One file, whole — a document or an inbox item (`inbox: true`). Carries the
 *  `fingerprint` a save hands back. */
export function getFile(path: string): Promise<FileOut> {
  return unwrap(getApiClient().GET("/knowledge/file", { params: { query: { path } } }));
}

/**
 * Save an edited document's body; its frontmatter is kept as it is on disk
 * (see "Save a document edited in the web UI"). `expected_fingerprint` is the
 * `fingerprint` the read carried: a file changed since is refused with 409
 * `KNOWLEDGE_FILE_CONFLICT` and left untouched. An inbox item is refused as
 * `KNOWLEDGE_PATH_UNSAFE`. Resolves with the file as saved, new fingerprint
 * included.
 */
export function saveFile(payload: FileSave): Promise<FileOut> {
  return unwrap(getApiClient().PUT("/knowledge/file", { body: payload }));
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
  return unwrapVoid(getApiClient().DELETE("/knowledge/file", { params: { query: { path } } }));
}

// --- curation ---------------------------------------------------------------

/**
 * Curate one collection now: the daemon runs one pass per pending item —
 * inbox items oldest first, then documents edited since curation last saw
 * them — until none is left, each pass still bounded, stopping at the first
 * that fails. The answer lists every pass's outcome; progress (n of m) is on
 * the in-flight list (`/upkeep/runs`) while the request is open.
 *
 * `document` curates just that document. With no internal model configured
 * the run comes back `no_model`, having promoted the inbox as it stood — a
 * clean 200. A second run over the same collection is refused with 409
 * `UPKEEP_ALREADY_RUNNING` rather than queued.
 */
export function curateCollection(uid: string, document?: string | null): Promise<CurationRunOut> {
  return unwrap(
    getApiClient().POST("/knowledge/collections/{uid}/curate", {
      params: { path: { uid } },
      body: { document: document ?? null },
    }),
  );
}

// --- history ------------------------------------------------------------------

/**
 * Recent changes across every collection, or one (`collection` is its NAME),
 * newest first, with the items still waiting in each inbox (see "Keep every
 * document's history and undo a pass as a whole").
 */
export function listChanges(params: {
  collection?: string | null;
  limit?: number;
}): Promise<ChangesOut> {
  return unwrap(
    getApiClient().GET("/knowledge/changes", {
      params: {
        query: {
          // An empty collection or a zero limit is "not given", as before.
          ...(params.collection ? { collection: params.collection } : {}),
          ...(params.limit ? { limit: params.limit } : {}),
        },
      },
    }),
  );
}

/** One change in full: every document it touched, with its diff. */
export function getChange(version: string): Promise<ChangeDetailOut> {
  return unwrap(
    getApiClient().GET("/knowledge/changes/{version}", { params: { path: { version } } }),
  );
}

/**
 * Undo a curation pass as a whole: every document it wrote goes back to how
 * it was before, as a new change naming the user. Refused with 409
 * `KNOWLEDGE_UNDO_CONFLICT` (details name the `document`) when a later change
 * to one of them would be lost; nothing is written then.
 */
export function undoPass(version: string): Promise<ChangeOut> {
  return unwrap(
    getApiClient().POST("/knowledge/changes/{version}/undo", { params: { path: { version } } }),
  );
}

/** A document's versions, newest first, each with its writer and time. */
export function getHistory(path: string): Promise<DocumentHistoryOut> {
  return unwrap(getApiClient().GET("/knowledge/history", { params: { query: { path } } }));
}

/** What one version did to the document, against the version before it. */
export function getVersionDiff(path: string, version: string): Promise<VersionDiffOut> {
  return unwrap(
    getApiClient().GET("/knowledge/history/diff", { params: { query: { path, version } } }),
  );
}

/** A document's body as one version left it — what Compare with current reads. */
export function getVersionBody(path: string, version: string): Promise<VersionBodyOut> {
  return unwrap(
    getApiClient().GET("/knowledge/history/version", { params: { query: { path, version } } }),
  );
}

/**
 * Put back what a delete removed — a document, or a whole collection with its
 * documents, README and waiting items — as one new change naming the user.
 * Refused with 409 when the path (`KNOWLEDGE_RESTORE_CONFLICT`) or the
 * collection's name (`KNOWLEDGE_COLLECTION_EXISTS`) is taken again.
 */
export function restoreDeleted(version: string): Promise<ChangeOut> {
  return unwrap(
    getApiClient().POST("/knowledge/changes/{version}/restore", {
      params: { path: { version } },
    }),
  );
}

/** Rewrite a collection's description — the opening paragraph of its README.
 *  A collection has no title: its heading is its folder name. */
export function describeCollection(uid: string, description: string): Promise<CollectionOut> {
  return unwrap(
    getApiClient().PUT("/knowledge/collections/{uid}/description", {
      params: { path: { uid } },
      body: { description },
    }),
  );
}

/** Put one version back, as a NEW version naming the user — the past is never rewritten. */
export function restoreVersion(payload: { path: string; version: string }): Promise<FileOut> {
  return unwrap(getApiClient().POST("/knowledge/history/restore", { body: payload }));
}

// --- ingestion ----------------------------------------------------------------

/**
 * Convert an uploaded document into material for a collection. The Markdown
 * extracted from it joins the collection's inbox and is curated into the
 * documents by the next pass (`pending: true`); with no internal model
 * configured it is promoted to a document on the spot and `path` names it.
 * Neither the original nor the extracted Markdown is kept beyond that — the
 * documents are what the collection holds.
 */
export function uploadFile(params: {
  /** The collection's NAME: this lands material in its directory. */
  collection: string;
  file: File;
  /** Aborts the request — the upload dialog's Cancel while it converts. */
  signal?: AbortSignal;
}): Promise<IngestedDocumentOut> {
  const form = new FormData();
  form.append("file", params.file);
  form.append("collection", params.collection);
  // A FormData body goes out with no Content-Type: the browser sets the
  // multipart boundary itself. `body` only carries the generated type.
  return unwrap(
    getApiClient().POST("/knowledge/upload", {
      signal: params.signal,
      body: { collection: params.collection, file: "" },
      bodySerializer: () => form,
    }),
  );
}
