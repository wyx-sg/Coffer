// frontend/src/kinds/memory/api.ts
//
// Hand-written fetch helpers for the redesigned `memory` kind (spec 007).
// Stores are AUTO-PROVISIONED (global + per-project) — there is no create.
// There is NO llm_provider anymore: facts are written directly (no LLM at
// write time). Each fact carries name/description/body/actor. Retrieval
// is the shared engine (grep / keyword / vector). Agents access these stores
// only via the Coffer MCP gateway — Coffer keeps its own memory format and no
// longer projects into agents' native memory locations.

import { getCofferBaseUrl, getCofferToken } from "@/lib/auth";
import { ApiError } from "@/lib/api/errors";
import type {
  MemoryStoreListOut,
  MemoryStoreOut,
  MemoryStoreMetrics,
  FactListOut,
  FactInput,
  FactOut,
  RecallResponse,
} from "./types";

// Re-export the wire types + scope helpers so existing `import { … } from
// "./api"` call sites keep working after the split into types.ts.
export * from "./types";

function headers(extra: HeadersInit = {}): HeadersInit {
  return {
    "X-Coffer-Token": getCofferToken() ?? "",
    "X-Coffer-Actor": "user",
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
const storeBase = (name: string) => `${getCofferBaseUrl()}/memory_stores/${enc(name)}`;

export async function listMemoryStores(): Promise<MemoryStoreListOut> {
  const r = await fetch(`${getCofferBaseUrl()}/memory_stores`, { headers: headers() });
  await checkOk(r);
  return (await r.json()) as MemoryStoreListOut;
}

export async function getMemoryStore(store: string): Promise<MemoryStoreOut> {
  const r = await fetch(storeBase(store), { headers: headers() });
  await checkOk(r);
  return (await r.json()) as MemoryStoreOut;
}

export async function getMemoryStoreMetrics(store: string): Promise<MemoryStoreMetrics> {
  const r = await fetch(`${storeBase(store)}/metrics`, { headers: headers() });
  await checkOk(r);
  return (await r.json()) as MemoryStoreMetrics;
}

// Set or clear a store's display label (007 FR-017c). Passing null / "" clears
// it (revert to the project_root-derived or fallback name).
export async function renameMemoryStore(
  store: string,
  label: string | null,
): Promise<MemoryStoreOut> {
  const r = await fetch(`${storeBase(store)}/label`, {
    method: "PATCH",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify({ label }),
  });
  await checkOk(r);
  return (await r.json()) as MemoryStoreOut;
}

export async function listFacts(store: string, limit = 50, offset = 0): Promise<FactListOut> {
  const r = await fetch(`${storeBase(store)}/facts?limit=${limit}&offset=${offset}`, {
    headers: headers(),
  });
  await checkOk(r);
  return (await r.json()) as FactListOut;
}

export async function getFact(store: string, factId: string): Promise<FactOut> {
  const r = await fetch(`${storeBase(store)}/facts/${enc(factId)}`, { headers: headers() });
  await checkOk(r);
  return (await r.json()) as FactOut;
}

export async function addFact(store: string, input: FactInput): Promise<FactOut> {
  const r = await fetch(`${storeBase(store)}/facts`, {
    method: "POST",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  await checkOk(r);
  return (await r.json()) as FactOut;
}

export async function deleteFact(store: string, factId: string): Promise<void> {
  const r = await fetch(`${storeBase(store)}/facts/${enc(factId)}`, {
    method: "DELETE",
    headers: headers(),
  });
  await checkOk(r);
}

export async function clearFacts(store: string): Promise<number> {
  const r = await fetch(`${storeBase(store)}/facts`, {
    method: "DELETE",
    headers: headers(),
  });
  await checkOk(r);
  const data = (await r.json()) as { cleared: number };
  return data.cleared;
}

export async function recall(
  store: string,
  query: string,
  opts: { topK?: number; scope?: "global" | "project" | "both" } = {},
): Promise<RecallResponse> {
  // External retrieval is "one query → one answer": the backend auto-selects
  // the strategy, so the request carries no `mode` and the response no longer
  // returns `mode`/`fallback`.
  const body: Record<string, unknown> = { query, top_k: opts.topK ?? 5 };
  if (opts.scope) body.scope = opts.scope;
  const r = await fetch(`${storeBase(store)}/recall`, {
    method: "POST",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await checkOk(r);
  return (await r.json()) as RecallResponse;
}
