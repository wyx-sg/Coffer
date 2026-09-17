// frontend/src/lib/api/knowledge.ts
//
// Request helpers for the `knowledge` kind. Nothing here retrieves and nothing
// here reads an index: a collection is two folders (`sources/` and `topics/`)
// walked a level at a time, frontmatter read at call time (ADR
// knowledge-is-plain-files), so a file someone dropped into `sources/` by hand
// is visible on the very next call and there is nothing to reindex or re-embed.
//
// There is no `search` and no `grep` here because the daemon serves neither
// (FR-050). Writing and deleting reach `sources/` only — `topics/` is
// curation's lane, and `curateCollection` is the one way anything gets into it.
//
// Deleting a COLLECTION is deliberately absent: a collection is one `knowledge`
// Resource, so it goes through the kind-agnostic
// `DELETE /resources/knowledge/{name}` (`useDeleteResource`) like every other
// kind. Only files are deleted here.
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
 * List ONE level of ONE lane: the immediate subdirectories and files under
 * `path` (relative to the knowledge root, lane included —
 * `shopee/sources/account`). The tree descends a level per request, and the
 * page asks once per lane rather than this route carrying a lane parameter the
 * path already spells.
 */
export function getTree(path: string): Promise<TreeOut> {
  return call<TreeOut>(`${ROOT}/tree?path=${enc(path)}`);
}

export function getFile(path: string): Promise<FileOut> {
  return call<FileOut>(`${ROOT}/file?path=${enc(path)}`);
}

/**
 * Remove ONE source. `path` is relative to the knowledge root, the same string
 * the tree and `getFile` use — the daemon refuses anything that escapes it,
 * and refuses a `topics/` path outright: a topic document is derived and is
 * removed by being retired in a pass, never from here (FR-027).
 *
 * A source is the only copy: there is no index to fall out of step and nothing
 * to restore it from but the sync remote's history, which is why every caller
 * confirms first. 204, so nothing comes back.
 */
export function deleteFile(path: string): Promise<void> {
  return call<void>(`${ROOT}/file?path=${enc(path)}`, { method: "DELETE" });
}

// --- curation ---------------------------------------------------------------

/**
 * Run ONE curation pass over one collection now — the manual trigger for the
 * pass the background sweep otherwise runs on an interval. It reads one source
 * and writes only `topics/`.
 *
 * `source` names a particular source to fold in; omitted, the pass takes the
 * oldest one whose watermark is behind its own modification time, which is
 * what the page's button wants. A pass with no internal model configured comes
 * back `no_model` — a clean 200, not an error — so every status here is
 * something the page reports rather than something it treats as a failure.
 *
 * A second pass over the same collection is refused with 409
 * `UPKEEP_ALREADY_RUNNING` rather than queued (FR-039).
 */
export function curateCollection(name: string, source?: string | null): Promise<CurationOut> {
  return call<CurationOut>(`${ROOT}/collections/${enc(name)}/curate`, {
    method: "POST",
    body: { source: source ?? null },
  });
}

// --- ingestion ----------------------------------------------------------------

/**
 * Convert an uploaded document into an ordinary source. `folder` is relative to
 * the collection's `sources/` LANE (not the knowledge root and not the
 * collection root) — mirroring `IngestService.ingest`, which joins it onto that
 * lane itself, so an upload can never be aimed at `topics/`.
 *
 * Both the original and the Markdown extracted from it land in `sources/`; the
 * response names the original's path, which is an ordinary visible file the
 * tree lists beside its conversion.
 */
export function uploadFile(params: {
  collection: string;
  folder?: string | null;
  file: File;
}): Promise<IngestedDocumentOut> {
  const form = new FormData();
  form.append("file", params.file);
  form.append("collection", params.collection);
  if (params.folder) form.append("folder", params.folder);
  // A FormData body goes out with no Content-Type: the browser sets the
  // multipart boundary itself (see `call`).
  return call<IngestedDocumentOut>(`${ROOT}/upload`, { method: "POST", body: form });
}
