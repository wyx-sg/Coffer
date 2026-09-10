// frontend/src/kinds/knowledge/document-api.ts
//
// Fetch helpers for the DOCUMENT lane of a knowledge scope
// (`/api/v1/knowledge/{scope}/documents*` plus reindex / search / grep /
// check-sources). Uploads of ANY format are converted to Markdown on disk (the
// source of truth); external retrieval is "one query → one answer" (the backend
// auto-selects the strategy).
//
// Documents live in `<scope>/docs/` and are a DIFFERENT lane from the notes
// an agent wrote — these reads never return entries, and `document_count` never
// includes them. api.ts re-exports everything here.

import { checkOk, enc, headers, scopeBase } from "./client";
import type {
  DocumentDetailOut,
  DocumentListOut,
  DocumentOut,
  DocumentStatusResponse,
  GrepResponse,
  ReembedBatchRequest,
  ReembedBatchResponse,
  ReindexResult,
  SourceCheckResponse,
} from "./document-types";

// Re-export the document wire types so `import { … } from "./api"` sees them.
export * from "./document-types";

export async function listDocuments(
  scope: string,
  limit = 50,
  offset = 0,
  q?: string,
): Promise<DocumentListOut> {
  // `q` is an optional case-insensitive title filter applied server-side; the
  // returned `total` reflects the filtered count so pagination stays correct.
  const qParam = q && q.trim() ? `&q=${enc(q)}` : "";
  const r = await fetch(`${scopeBase(scope)}/documents?limit=${limit}&offset=${offset}${qParam}`, {
    headers: headers(),
  });
  await checkOk(r);
  return (await r.json()) as DocumentListOut;
}

export async function getDocument(scope: string, documentId: string): Promise<DocumentDetailOut> {
  const r = await fetch(`${scopeBase(scope)}/documents/${enc(documentId)}`, { headers: headers() });
  await checkOk(r);
  return (await r.json()) as DocumentDetailOut;
}

export async function ingestDocument(
  scope: string,
  file: File,
  replace = false,
): Promise<DocumentOut> {
  const form = new FormData();
  form.append("file", file);
  form.append("replace", String(replace));
  const r = await fetch(`${scopeBase(scope)}/documents`, {
    method: "POST",
    headers: headers(),
    body: form,
  });
  await checkOk(r);
  return (await r.json()) as DocumentOut;
}

export async function editDocument(
  scope: string,
  documentId: string,
  markdown: string,
): Promise<DocumentOut> {
  const r = await fetch(`${scopeBase(scope)}/documents/${enc(documentId)}`, {
    method: "PUT",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify({ markdown }),
  });
  await checkOk(r);
  return (await r.json()) as DocumentOut;
}

export async function deleteDocument(scope: string, documentId: string): Promise<void> {
  const r = await fetch(`${scopeBase(scope)}/documents/${enc(documentId)}`, {
    method: "DELETE",
    headers: headers(),
  });
  await checkOk(r);
}

export async function reconvertDocument(scope: string, documentId: string): Promise<DocumentOut> {
  // 409 RECONVERSION_BLOCKED when the document was hand-edited
  // (source_mode=edited); surfaced to callers as a typed ApiError.
  const r = await fetch(`${scopeBase(scope)}/documents/${enc(documentId)}/reconvert`, {
    method: "POST",
    headers: headers(),
  });
  await checkOk(r);
  return (await r.json()) as DocumentOut;
}

export async function updateFromSource(scope: string, documentId: string): Promise<DocumentOut> {
  // Re-ingests one document from its external source file. Refused with a typed
  // ApiError (via checkOk) when source_mode=edited — the local edits would be
  // clobbered — mirroring reconvert's blocked case.
  const r = await fetch(`${scopeBase(scope)}/documents/${enc(documentId)}/update-source`, {
    method: "POST",
    headers: headers(),
  });
  await checkOk(r);
  return (await r.json()) as DocumentOut;
}

export async function reindexScope(scope: string): Promise<ReindexResult> {
  const r = await fetch(`${scopeBase(scope)}/reindex`, { method: "POST", headers: headers() });
  await checkOk(r);
  return (await r.json()) as ReindexResult;
}

export async function checkSources(scope: string): Promise<SourceCheckResponse> {
  // Scans every document with a tracked external source file and reports its
  // status (unchanged / changed / missing / edited / updated). With the scope's
  // auto_update_sources flag on, changed docs are re-ingested and reported as
  // "updated"; web-uploaded docs have no source_path and never appear.
  const r = await fetch(`${scopeBase(scope)}/check-sources`, {
    method: "POST",
    headers: headers(),
  });
  await checkOk(r);
  return (await r.json()) as SourceCheckResponse;
}

export async function grepDocuments(
  scope: string,
  pattern: string,
  opts: { maxMatches?: number } = {},
): Promise<GrepResponse> {
  const r = await fetch(`${scopeBase(scope)}/grep`, {
    method: "POST",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify({ pattern, max_matches: opts.maxMatches ?? 100 }),
  });
  await checkOk(r);
  return (await r.json()) as GrepResponse;
}

export async function reembedDocuments(
  scope: string,
  body: ReembedBatchRequest,
): Promise<ReembedBatchResponse> {
  // Enqueue per-document re-embed off the request path (202). Either an explicit
  // `document_ids` set or `all: true`; documents not pending an embed are skipped.
  const r = await fetch(`${scopeBase(scope)}/documents/reembed-batch`, {
    method: "POST",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await checkOk(r);
  return (await r.json()) as ReembedBatchResponse;
}

export async function getDocumentStatus(scope: string): Promise<DocumentStatusResponse> {
  const r = await fetch(`${scopeBase(scope)}/documents/status`, { headers: headers() });
  await checkOk(r);
  return (await r.json()) as DocumentStatusResponse;
}
