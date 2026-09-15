// frontend/src/lib/api/knowledge.ts
//
// Request helpers for the `knowledge` kind. Nothing here reads an index: the
// catalogue is produced by walking `~/.coffer/knowledge/` and reading
// frontmatter at call time (ADR knowledge-is-plain-files), so a file someone
// dropped into the folder by hand is visible on the very next call and there
// is nothing to reindex, reconcile or re-embed.
//
// Deleting a COLLECTION is deliberately absent: a collection is one `knowledge`
// Resource, so it goes through the kind-agnostic
// `DELETE /resources/knowledge/{name}` (`useDeleteResource`) like every other
// kind. Only files are deleted here.
//
// Transport via the shared `call` (agents/frontend.md §4); wire types in
// `knowledgeTypes.ts`.

import { call, enc } from "@/lib/api/call";
import type {
  CollectionListOut,
  CollectionOut,
  FileOut,
  IngestedDocumentOut,
  SearchOut,
  TidyOut,
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
 * List ONE level of the tree: the immediate subdirectories and files under
 * `path` (relative to the knowledge root). The catalogue descends a level per
 * request — there is no recursive listing to ask for.
 */
export function getTree(path: string): Promise<TreeOut> {
  return call<TreeOut>(`${ROOT}/tree?path=${enc(path)}`);
}

export function getFile(path: string): Promise<FileOut> {
  return call<FileOut>(`${ROOT}/file?path=${enc(path)}`);
}

export function deleteFile(path: string): Promise<void> {
  return call<void>(`${ROOT}/file?path=${enc(path)}`, { method: "DELETE" });
}

// --- tidy -------------------------------------------------------------------

/**
 * Run the tidy pass over one collection NOW — the manual trigger for the pass
 * the background worker otherwise runs on an interval (off by default). Only
 * `status` is read here: a pass with no internal model configured returns a
 * clean no-op status rather than an error.
 */
export function tidyCollection(name: string): Promise<TidyOut> {
  return call<TidyOut>(`${ROOT}/collections/${enc(name)}/tidy`, { method: "POST" });
}

// --- search -------------------------------------------------------------------

/**
 * Find the files a word or phrase appears in, across the files the caller may
 * see. `collection` narrows to one; omitted, every visible collection is
 * searched. Matching is literal — there is no ranking and no retrieval mode
 * (FR-024).
 */
export function search(query: string, collection?: string | null): Promise<SearchOut> {
  return call<SearchOut>(`${ROOT}/search`, {
    method: "POST",
    body: { query, collection: collection ?? null },
  });
}

// --- ingestion ----------------------------------------------------------------

/**
 * Convert an uploaded document into an ordinary knowledge file. `directory` is
 * relative to the COLLECTION root (not the knowledge root) — mirroring
 * `IngestService.ingest`, which joins it onto `collection` itself.
 */
export function uploadFile(params: {
  collection: string;
  directory?: string | null;
  file: File;
}): Promise<IngestedDocumentOut> {
  const form = new FormData();
  form.append("file", params.file);
  form.append("collection", params.collection);
  if (params.directory) form.append("directory", params.directory);
  // A FormData body goes out with no Content-Type: the browser sets the
  // multipart boundary itself (see `call`).
  return call<IngestedDocumentOut>(`${ROOT}/upload`, { method: "POST", body: form });
}
