// frontend/src/kinds/knowledge_base/api.ts
//
// Minimal fetch-based API helpers for the knowledge_base kind. These mirror
// the OpenAPI contract in specs/006-knowledge-base/contracts/api.openapi.yaml.
// When openapi-typescript regenerates `lib/api/types.ts` to include these
// routes, we can switch to the typed client — until then, fetch + interfaces.

import { getCofferBaseUrl, getCofferToken } from "@/lib/auth";

export interface KnowledgeBaseConfigOut {
  embedding_model: string;
  chunk_size: number;
  chunk_overlap: number;
  max_document_bytes: number;
}

export interface KnowledgeBaseOut {
  ref: string;
  kind: string;
  name: string;
  description: string | null;
  config: KnowledgeBaseConfigOut;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface DocumentOut {
  id: string;
  kb_name: string;
  filename: string;
  extension: string;
  size_bytes: number;
  sha256: string;
  chunk_count: number;
  ingested_at: string;
}

export interface DocumentListOut {
  documents: DocumentOut[];
  total: number;
}

export interface SearchHit {
  text: string;
  document_id: string;
  filename: string;
  score: number;
  position: number;
}

function headers(extra: HeadersInit = {}): HeadersInit {
  return {
    "X-Coffer-Token": getCofferToken() ?? "",
    "X-Coffer-Actor": "ui",
    ...extra,
  };
}

async function checkOk(r: Response): Promise<Response> {
  if (!r.ok) {
    let detail: unknown = null;
    try {
      detail = await r.json();
    } catch {
      detail = await r.text();
    }
    throw new Error(
      `HTTP ${r.status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`,
    );
  }
  return r;
}

export async function createKnowledgeBase(payload: {
  name: string;
  description: string | null;
  config: KnowledgeBaseConfigOut;
}): Promise<KnowledgeBaseOut> {
  const r = await fetch(`${getCofferBaseUrl()}/knowledge_bases`, {
    method: "POST",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await checkOk(r);
  return (await r.json()) as KnowledgeBaseOut;
}

export async function listDocuments(
  kbName: string,
  limit = 50,
  offset = 0,
): Promise<DocumentListOut> {
  const r = await fetch(
    `${getCofferBaseUrl()}/knowledge_bases/${encodeURIComponent(kbName)}/documents?limit=${limit}&offset=${offset}`,
    { headers: headers() },
  );
  await checkOk(r);
  return (await r.json()) as DocumentListOut;
}

export async function ingestDocument(
  kbName: string,
  file: File,
  replace = false,
): Promise<DocumentOut> {
  const form = new FormData();
  form.append("file", file);
  form.append("replace", String(replace));
  const r = await fetch(
    `${getCofferBaseUrl()}/knowledge_bases/${encodeURIComponent(kbName)}/documents`,
    {
      method: "POST",
      headers: headers(),
      body: form,
    },
  );
  await checkOk(r);
  return (await r.json()) as DocumentOut;
}

export async function deleteDocument(kbName: string, documentId: string): Promise<void> {
  const r = await fetch(
    `${getCofferBaseUrl()}/knowledge_bases/${encodeURIComponent(kbName)}/documents/${encodeURIComponent(documentId)}`,
    { method: "DELETE", headers: headers() },
  );
  await checkOk(r);
}

export async function searchKnowledgeBase(
  kbName: string,
  query: string,
  topK = 5,
): Promise<SearchHit[]> {
  const r = await fetch(
    `${getCofferBaseUrl()}/knowledge_bases/${encodeURIComponent(kbName)}/search`,
    {
      method: "POST",
      headers: { ...headers(), "Content-Type": "application/json" },
      body: JSON.stringify({ query, top_k: topK }),
    },
  );
  await checkOk(r);
  const data = (await r.json()) as { hits: SearchHit[] };
  return data.hits;
}

export async function getKnowledgeBaseMetrics(
  kbName: string,
): Promise<{ document_count: number; disk_bytes: number }> {
  const r = await fetch(
    `${getCofferBaseUrl()}/knowledge_bases/${encodeURIComponent(kbName)}/metrics`,
    { headers: headers() },
  );
  await checkOk(r);
  return (await r.json()) as { document_count: number; disk_bytes: number };
}
