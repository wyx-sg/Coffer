// frontend/src/kinds/memory/api.ts
import { getCofferBaseUrl, getCofferToken } from "@/lib/auth";

export interface MemoryStoreConfigOut {
  embedding_model: string;
  llm_provider: "none" | "ollama" | "openai";
  llm_model: string | null;
  llm_endpoint: string | null;
  llm_credential_ref: string | null;
  max_memory_chars: number;
}

export interface MemoryStoreOut {
  ref: string;
  kind: string;
  name: string;
  description: string | null;
  config: MemoryStoreConfigOut;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface MemoryOut {
  id: string;
  store_name: string;
  text: string;
  actor: "agent" | "user";
  created_at: string;
  updated_at: string;
}

export interface MemoryListOut {
  memories: MemoryOut[];
  total: number;
}

export interface MemorySearchHit {
  id: string;
  text: string;
  score: number;
  created_at: string;
}

function headers(extra: HeadersInit = {}): HeadersInit {
  return {
    "X-Coffer-Token": getCofferToken() ?? "",
    "X-Coffer-Actor": "user",
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

export async function createMemoryStore(payload: {
  name: string;
  description: string | null;
  config: MemoryStoreConfigOut;
}): Promise<MemoryStoreOut> {
  const r = await fetch(`${getCofferBaseUrl()}/memory_stores`, {
    method: "POST",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await checkOk(r);
  return (await r.json()) as MemoryStoreOut;
}

export async function listMemories(store: string, limit = 50, offset = 0): Promise<MemoryListOut> {
  const r = await fetch(
    `${getCofferBaseUrl()}/memory_stores/${encodeURIComponent(store)}/memories?limit=${limit}&offset=${offset}`,
    { headers: headers() },
  );
  await checkOk(r);
  return (await r.json()) as MemoryListOut;
}

export async function addMemory(store: string, text: string): Promise<MemoryOut> {
  const r = await fetch(
    `${getCofferBaseUrl()}/memory_stores/${encodeURIComponent(store)}/memories`,
    {
      method: "POST",
      headers: { ...headers(), "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    },
  );
  await checkOk(r);
  return (await r.json()) as MemoryOut;
}

export async function updateMemory(store: string, id: string, text: string): Promise<MemoryOut> {
  const r = await fetch(
    `${getCofferBaseUrl()}/memory_stores/${encodeURIComponent(store)}/memories/${encodeURIComponent(id)}`,
    {
      method: "PATCH",
      headers: { ...headers(), "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    },
  );
  await checkOk(r);
  return (await r.json()) as MemoryOut;
}

export async function deleteMemory(store: string, id: string): Promise<void> {
  const r = await fetch(
    `${getCofferBaseUrl()}/memory_stores/${encodeURIComponent(store)}/memories/${encodeURIComponent(id)}`,
    { method: "DELETE", headers: headers() },
  );
  await checkOk(r);
}

export async function clearMemories(store: string): Promise<number> {
  const r = await fetch(
    `${getCofferBaseUrl()}/memory_stores/${encodeURIComponent(store)}/memories/clear`,
    { method: "POST", headers: headers() },
  );
  await checkOk(r);
  const data = (await r.json()) as { cleared: number };
  return data.cleared;
}

export async function searchMemories(
  store: string,
  query: string,
  topK = 5,
): Promise<MemorySearchHit[]> {
  const r = await fetch(`${getCofferBaseUrl()}/memory_stores/${encodeURIComponent(store)}/search`, {
    method: "POST",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK }),
  });
  await checkOk(r);
  const data = (await r.json()) as { hits: MemorySearchHit[] };
  return data.hits;
}

export async function getMemoryStoreMetrics(
  store: string,
): Promise<{ memory_count: number; disk_bytes: number }> {
  const r = await fetch(
    `${getCofferBaseUrl()}/memory_stores/${encodeURIComponent(store)}/metrics`,
    { headers: headers() },
  );
  await checkOk(r);
  return (await r.json()) as { memory_count: number; disk_bytes: number };
}
