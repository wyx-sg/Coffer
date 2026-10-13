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
// upload here, an agent's file in `.inbox/` — and becomes a document as it is
// (see "Promote submitted material at once").
//
// Deleting a COLLECTION is deliberately absent: a collection is one `knowledge`
// Resource, so it goes through the kind-agnostic `DELETE /resources/{uid}`
// (`useDeleteResource`) like every other kind. Only files are deleted here.
//
// Two vocabularies meet in this module and both are correct. A collection's
// description addresses it, so it takes the collection's `uid`. The file routes
// address a place on disk, and a collection's directory is named after it, so
// `path` and `collection` are NAMES — the same strings the tree hands back. A
// caller that holds a `CollectionOut` has both and picks by what it is asking for.
//
// Transport via the typed client (.agents/frontend.md §4); wire types in
// `knowledgeTypes.ts`.

import { getApiClient, unwrap, unwrapVoid } from "@/lib/api/client";
import type {
  ChangeOut,
  ChangesOut,
  CheckOut,
  CollectionFilesOut,
  CollectionListOut,
  CollectionOut,
  FileOut,
  HandoffOut,
  IngestedDocumentOut,
  TreeOut,
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

/** Share a folder the person keeps themselves with every agent; nothing is copied. */
export function linkFolder(payload: {
  folder: string;
  name?: string | null;
}): Promise<CollectionOut> {
  return unwrap(getApiClient().POST("/knowledge/collections/link", { body: payload }));
}

// --- catalogue --------------------------------------------------------------

/**
 * List ONE level of a collection: the immediate subdirectories and documents
 * under `path`, relative to the knowledge root — `shopee` for the collection
 * itself, `shopee/account` for a folder inside it. The tree descends a level
 * per request. The collection's own `README.md` never appears, nor does any
 * dot-prefixed entry (see "Hide every dot-prefixed entry").
 */
export function getTree(path: string): Promise<TreeOut> {
  return unwrap(getApiClient().GET("/knowledge/tree", { params: { query: { path } } }));
}

/** One document, whole. */
export function getFile(path: string): Promise<FileOut> {
  return unwrap(getApiClient().GET("/knowledge/file", { params: { query: { path } } }));
}

/**
 * One picture a document shows (an upload's, under `assets/`), as a data URL
 * an `<img>` can show: the route needs the session token, which an `<img src>`
 * cannot send. `null` when it is not a picture or is gone.
 */
export async function getAsset(path: string): Promise<string | null> {
  const { data, response } = await getApiClient().GET("/knowledge/asset", {
    params: { query: { path } },
    parseAs: "blob",
  });
  if (response.status !== 200 || !(data instanceof Blob) || data.size === 0) return null;
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : null);
    reader.onerror = () => resolve(null);
    reader.readAsDataURL(data);
  });
}

/**
 * Remove ONE document — any of them (see "Let only a person delete a document"). `path` is relative to the knowledge
 * root, the same string the tree and `getFile` use, and the daemon refuses anything that
 * escapes it.
 *
 * The delete is one commit in the vault's history, so its toast offers Undo
 * (`restoreDeleted`); after that, git brings the file back. 204, so nothing
 * comes back.
 */
export function deleteFile(path: string): Promise<void> {
  return unwrapVoid(getApiClient().DELETE("/knowledge/file", { params: { query: { path } } }));
}

/** A collection's mechanical check (see "Check a collection mechanically on
 *  every read"): its findings, computed from its files on this read. */
export function getCheck(uid: string): Promise<CheckOut> {
  return unwrap(
    getApiClient().GET("/knowledge/collections/{uid}/check", { params: { path: { uid } } }),
  );
}

/** Every page and source of a collection with its title, page type and
 *  waiting mark: a collection page's Contents, and the titles its To do and
 *  Change log show (see "Show a collection's contents by page type"). */
export function getCollectionFiles(uid: string): Promise<CollectionFilesOut> {
  return unwrap(
    getApiClient().GET("/knowledge/collections/{uid}/files", { params: { path: { uid } } }),
  );
}

// --- tidy ---------------------------------------------------------------------

/** The prompt that hands tidying every collection to the person's agent: the
 *  Knowledge page's Tidy all (see "Hand a tidy to the agent"). One collection's
 *  prompt is the `tidy_handoff` on its read. */
export function getTidyHandoff(): Promise<HandoffOut> {
  return unwrap(getApiClient().GET("/knowledge/tidy-handoff"));
}

// --- changes ------------------------------------------------------------------

/**
 * Recent changes across every collection, or one (`collection` is its NAME),
 * newest first (see "Follow edits across collections in one feed"): a
 * collection page's Change log, and the delete an Undo restores. `cursor` is
 * the previous page's `next_cursor`.
 */
export function listChanges(params: {
  collection?: string | null;
  limit?: number;
  cursor?: string | null;
  signal?: AbortSignal;
}): Promise<ChangesOut> {
  return unwrap(
    getApiClient().GET("/knowledge/changes", {
      signal: params.signal,
      params: {
        query: {
          // An empty collection or a zero limit is "not given", as before.
          ...(params.collection ? { collection: params.collection } : {}),
          ...(params.limit ? { limit: params.limit } : {}),
          ...(params.cursor ? { cursor: params.cursor } : {}),
        },
      },
    }),
  );
}

/**
 * Put back what a delete removed — a document, or a whole collection with its
 * documents and README — as one new change naming the user.
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

/**
 * Put every file a change touched back as it was before it, as one new change
 * naming the user: a tidy's **Undo this tidy** (see "Undo a tidy"). Refused
 * with 409 `KNOWLEDGE_UNDO_CONFLICT`, naming the files, when one was edited
 * since; `force` discards those edits.
 */
export function undoChange(version: string, force = false): Promise<ChangeOut> {
  return unwrap(
    getApiClient().POST("/knowledge/changes/{version}/undo", {
      params: { path: { version } },
      body: { force },
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

// --- ingestion ----------------------------------------------------------------

/**
 * Convert an uploaded file into a source of a collection, at once (see
 * "Promote submitted material at once"); `path` names it. Only the Markdown
 * is kept (see "Keep every upload as a Markdown source").
 */
export function uploadFile(params: {
  /** The collection's NAME: this lands material in its directory. */
  collection: string;
  file: File;
  /** Import a page already imported again, marking the older source replaced
   *  (spec knowledge "Import a Confluence page as a readable source with its
   *  attachments"). */
  replace?: boolean;
  /** Aborts the request — the upload dialog's Cancel while it converts. */
  signal?: AbortSignal;
}): Promise<IngestedDocumentOut> {
  const form = new FormData();
  form.append("file", params.file);
  form.append("collection", params.collection);
  if (params.replace) form.append("replace", "true");
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
