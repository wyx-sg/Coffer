// frontend/src/kinds/knowledge_base/api.ts
//
// Hand-written fetch-based API helpers for the knowledge_base kind. These
// mirror the redesigned OpenAPI contract in
// specs/006-knowledge-base/contracts/api.openapi.yaml. Uploads of ANY format
// are converted to Markdown on disk (the source of truth); retrieval has three
// modes (grep / keyword / vector). The KB is user-curated; agents read it
// read-only over the MCP gateway. We keep fetch + interfaces (not codegen —
// codegen only covers spec 001).

import { getCofferBaseUrl, getCofferToken } from "@/lib/auth";
import { ApiError } from "@/lib/api/errors";
import type {
  RetrievalMode,
  KnowledgeBaseConfigOut,
  KnowledgeBaseOut,
  DocumentOut,
  DocumentListOut,
  DocumentDetailOut,
  SearchResponse,
  GrepResponse,
  ReindexResult,
  KnowledgeBaseMetrics,
} from "./types";

// Re-export the wire types so existing `import { … } from "./api"` call sites
// keep working after the split into types.ts.
export * from "./types";

function headers(extra: HeadersInit = {}): HeadersInit {
  return {
    "X-Coffer-Token": getCofferToken() ?? "",
    "X-Coffer-Actor": "ui",
    ...extra,
  };
}

async function checkOk(r: Response): Promise<Response> {
  if (!r.ok) {
    // Parse the `{ error: { code, message, details } }` envelope and surface a
    // typed ApiError so `translateApiError(t, …)` can localize it. Mirrors
    // lib/api/fs.ts; a plain Error would leak the raw JSON envelope to users.
    const data = (await r.json().catch(() => null)) as {
      error?: { code?: string; message?: string };
    } | null;
    const err = data?.error;
    throw new ApiError(
      err?.code ?? "INTERNAL_ERROR",
      err?.message ?? `request failed: ${r.status}`,
    );
  }
  return r;
}

const enc = encodeURIComponent;
const kbBase = (name: string) => `${getCofferBaseUrl()}/knowledge_bases/${enc(name)}`;
// Config reads/updates go through the kind-agnostic resource endpoints
// (PATCH /resources/{kind}/{name} replaces the whole config server-side, so
// callers must send the merged object — see updateKnowledgeBaseConfig).
const resourceBase = (name: string) =>
  `${getCofferBaseUrl()}/resources/knowledge_base/${enc(name)}`;

export async function createKnowledgeBase(payload: {
  name: string;
  description: string | null;
  config: Partial<KnowledgeBaseConfigOut>;
}): Promise<KnowledgeBaseOut> {
  const r = await fetch(`${getCofferBaseUrl()}/knowledge_bases`, {
    method: "POST",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await checkOk(r);
  return (await r.json()) as KnowledgeBaseOut;
}

export async function getKnowledgeBase(name: string): Promise<KnowledgeBaseOut> {
  const r = await fetch(resourceBase(name), { headers: headers() });
  await checkOk(r);
  return (await r.json()) as KnowledgeBaseOut;
}

export async function updateKnowledgeBaseConfig(
  name: string,
  config: Partial<KnowledgeBaseConfigOut>,
): Promise<KnowledgeBaseOut> {
  // The backend replaces the stored config with this object (no deep merge),
  // so `config` must be the full desired config, not a delta (FR-019/FR-014).
  const r = await fetch(resourceBase(name), {
    method: "PATCH",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify({ config }),
  });
  await checkOk(r);
  return (await r.json()) as KnowledgeBaseOut;
}

export async function listDocuments(
  kbName: string,
  limit = 50,
  offset = 0,
): Promise<DocumentListOut> {
  const r = await fetch(`${kbBase(kbName)}/documents?limit=${limit}&offset=${offset}`, {
    headers: headers(),
  });
  await checkOk(r);
  return (await r.json()) as DocumentListOut;
}

export async function getDocument(kbName: string, documentId: string): Promise<DocumentDetailOut> {
  const r = await fetch(`${kbBase(kbName)}/documents/${enc(documentId)}`, {
    headers: headers(),
  });
  await checkOk(r);
  return (await r.json()) as DocumentDetailOut;
}

export async function ingestDocument(
  kbName: string,
  file: File,
  replace = false,
): Promise<DocumentOut> {
  const form = new FormData();
  form.append("file", file);
  form.append("replace", String(replace));
  const r = await fetch(`${kbBase(kbName)}/documents`, {
    method: "POST",
    headers: headers(),
    body: form,
  });
  await checkOk(r);
  return (await r.json()) as DocumentOut;
}

export async function editDocument(
  kbName: string,
  documentId: string,
  markdown: string,
): Promise<DocumentOut> {
  const r = await fetch(`${kbBase(kbName)}/documents/${enc(documentId)}`, {
    method: "PUT",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify({ markdown }),
  });
  await checkOk(r);
  return (await r.json()) as DocumentOut;
}

export async function deleteDocument(kbName: string, documentId: string): Promise<void> {
  const r = await fetch(`${kbBase(kbName)}/documents/${enc(documentId)}`, {
    method: "DELETE",
    headers: headers(),
  });
  await checkOk(r);
}

export async function reconvertDocument(kbName: string, documentId: string): Promise<DocumentOut> {
  // 409 RECONVERSION_BLOCKED when the document was hand-edited
  // (source_mode=edited); surfaced to callers as a typed ApiError.
  const r = await fetch(`${kbBase(kbName)}/documents/${enc(documentId)}/reconvert`, {
    method: "POST",
    headers: headers(),
  });
  await checkOk(r);
  return (await r.json()) as DocumentOut;
}

export async function reindexKnowledgeBase(kbName: string): Promise<ReindexResult> {
  const r = await fetch(`${kbBase(kbName)}/reindex`, {
    method: "POST",
    headers: headers(),
  });
  await checkOk(r);
  return (await r.json()) as ReindexResult;
}

export async function searchKnowledgeBase(
  kbName: string,
  query: string,
  opts: { topK?: number; mode?: RetrievalMode } = {},
): Promise<SearchResponse> {
  const body: Record<string, unknown> = { query, top_k: opts.topK ?? 5 };
  if (opts.mode) body.mode = opts.mode;
  const r = await fetch(`${kbBase(kbName)}/search`, {
    method: "POST",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await checkOk(r);
  return (await r.json()) as SearchResponse;
}

export async function grepKnowledgeBase(
  kbName: string,
  pattern: string,
  maxMatches = 100,
): Promise<GrepResponse> {
  const r = await fetch(`${kbBase(kbName)}/grep`, {
    method: "POST",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify({ pattern, max_matches: maxMatches }),
  });
  await checkOk(r);
  return (await r.json()) as GrepResponse;
}

export async function getKnowledgeBaseMetrics(kbName: string): Promise<KnowledgeBaseMetrics> {
  const r = await fetch(`${kbBase(kbName)}/metrics`, { headers: headers() });
  await checkOk(r);
  return (await r.json()) as KnowledgeBaseMetrics;
}
