// frontend/src/kinds/knowledge/api.ts
//
// Hand-written fetch helpers for the `knowledge` kind. Nothing here reads an
// index: the catalogue is produced by walking `~/.coffer/knowledge/` and
// reading frontmatter at call time (ADR knowledge-is-plain-files), so a file
// someone dropped into the folder by hand is visible on the very next call and
// there is nothing to reindex, reconcile or re-embed.
//
// Deleting a COLLECTION is deliberately absent: a collection is one `knowledge`
// Resource, so it goes through the kind-agnostic
// `DELETE /resources/knowledge/{name}` (`useDeleteResource`) like every other
// kind. Only files are deleted here.

import { checkOk, enc, headers, knowledgeRoot } from "./client";
import type {
  CollectionListOut,
  CollectionOut,
  FileOut,
  IndexStatusOut,
  IngestedDocumentOut,
  SearchOut,
  TidyOut,
  TreeOut,
} from "./types";

// Re-export the wire types so `import { … } from "./api"` sees one surface.
export * from "./types";

// --- collections ------------------------------------------------------------

export async function listCollections(): Promise<CollectionListOut> {
  const r = await fetch(`${knowledgeRoot()}/collections`, { headers: headers() });
  await checkOk(r);
  return (await r.json()) as CollectionListOut;
}

/**
 * Create a collection — one top-level folder, and one `knowledge` Resource so
 * per-agent scope can authorize it. The description lands in the folder's
 * `README.md`, which is where the catalogue reads it back from.
 */
export async function createCollection(payload: {
  name: string;
  description?: string | null;
}): Promise<CollectionOut> {
  const r = await fetch(`${knowledgeRoot()}/collections`, {
    method: "POST",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await checkOk(r);
  return (await r.json()) as CollectionOut;
}

// --- catalogue --------------------------------------------------------------

/**
 * List ONE level of the tree: the immediate subdirectories and files under
 * `path` (relative to the knowledge root). The catalogue descends a level per
 * request — there is no recursive listing to ask for.
 */
export async function getTree(path: string): Promise<TreeOut> {
  const r = await fetch(`${knowledgeRoot()}/tree?path=${enc(path)}`, { headers: headers() });
  await checkOk(r);
  return (await r.json()) as TreeOut;
}

export async function getFile(path: string): Promise<FileOut> {
  const r = await fetch(`${knowledgeRoot()}/file?path=${enc(path)}`, { headers: headers() });
  await checkOk(r);
  return (await r.json()) as FileOut;
}

export async function deleteFile(path: string): Promise<void> {
  const r = await fetch(`${knowledgeRoot()}/file?path=${enc(path)}`, {
    method: "DELETE",
    headers: headers(),
  });
  await checkOk(r);
}

// --- tidy -------------------------------------------------------------------

/**
 * Run the tidy pass over one collection NOW — the manual trigger for the pass
 * the background worker otherwise runs on an interval (off by default). Only
 * `status` is read here: a pass with no internal model configured returns a
 * clean no-op status rather than an error.
 */
export async function tidyCollection(name: string): Promise<TidyOut> {
  const r = await fetch(`${knowledgeRoot()}/collections/${enc(name)}/tidy`, {
    method: "POST",
    headers: headers(),
  });
  await checkOk(r);
  return (await r.json()) as TidyOut;
}

// --- ranked retrieval --------------------------------------------------------

/**
 * Ask a natural-language question over the files the caller may see.
 * `collection` narrows to one; omitted, every visible collection is searched.
 * The answer always says how it was found (`mode`) — there is no retrieval
 * mode to request (FR-024/FR-082).
 */
export async function search(query: string, collection?: string | null): Promise<SearchOut> {
  const r = await fetch(`${knowledgeRoot()}/search`, {
    method: "POST",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify({ query, collection: collection ?? null }),
  });
  await checkOk(r);
  return (await r.json()) as SearchOut;
}

/** What the disposable sidecar index holds right now. */
export async function getIndexStatus(): Promise<IndexStatusOut> {
  const r = await fetch(`${knowledgeRoot()}/index`, { headers: headers() });
  await checkOk(r);
  return (await r.json()) as IndexStatusOut;
}

/** Re-embed every visible file from scratch, discarding what is there. */
export async function rebuildIndex(): Promise<IndexStatusOut> {
  const r = await fetch(`${knowledgeRoot()}/index/rebuild`, {
    method: "POST",
    headers: headers(),
  });
  await checkOk(r);
  return (await r.json()) as IndexStatusOut;
}

// --- ingestion ----------------------------------------------------------------

/**
 * Convert an uploaded document into an ordinary knowledge file. `directory` is
 * relative to the COLLECTION root (not the knowledge root) — mirroring
 * `IngestService.ingest`, which joins it onto `collection` itself.
 */
export async function uploadFile(params: {
  collection: string;
  directory?: string | null;
  file: File;
}): Promise<IngestedDocumentOut> {
  const form = new FormData();
  form.append("file", params.file);
  form.append("collection", params.collection);
  if (params.directory) form.append("directory", params.directory);
  const r = await fetch(`${knowledgeRoot()}/upload`, {
    method: "POST",
    // No Content-Type: the browser sets the multipart boundary itself.
    headers: headers(),
    body: form,
  });
  await checkOk(r);
  return (await r.json()) as IngestedDocumentOut;
}
