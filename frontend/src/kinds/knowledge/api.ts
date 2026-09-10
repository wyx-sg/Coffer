// frontend/src/kinds/knowledge/api.ts
//
// Hand-written fetch helpers for the one `knowledge` kind. The two former route
// trees (`/memory_stores/*` and `/knowledge_bases/*`) collapse into
// `/api/v1/knowledge/*` with the SCOPE name as the path segment.
//
// `global` and `project-<ULID>` auto-provision on first use; a named collection
// is created deliberately through POST /knowledge (which rejects the two
// auto-scope name shapes with 422). Notes are written directly — no LLM at
// write time. Document helpers live in ./document-api; both are re-exported
// here so call sites keep one import path.

import { checkOk, enc, headers, knowledgeRoot, scopeBase } from "./client";
import type {
  EntryInput,
  EntryListOut,
  EntryOut,
  KnowledgeConfigPatch,
  ScopeListOut,
  ScopeMetrics,
  ScopeOut,
  TidyOut,
} from "./types";

// Re-export the wire types + scope helpers so `import { … } from "./api"` call
// sites see one surface for both lanes.
export * from "./types";
export * from "./document-api";
export { knowledgeRoot, scopeBase } from "./client";

// --- scopes -----------------------------------------------------------------

export async function listScopes(): Promise<ScopeListOut> {
  const r = await fetch(knowledgeRoot(), { headers: headers() });
  await checkOk(r);
  return (await r.json()) as ScopeListOut;
}

/**
 * Create a NAMED collection. `global` and `project-*` auto-provision on first
 * use and are rejected by the backend with 422, so the create form must never
 * offer those names.
 */
export async function createScope(payload: {
  name: string;
  description: string | null;
  config?: KnowledgeConfigPatch;
}): Promise<ScopeOut> {
  const r = await fetch(knowledgeRoot(), {
    method: "POST",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await checkOk(r);
  return (await r.json()) as ScopeOut;
}

export async function getScope(scope: string): Promise<ScopeOut> {
  const r = await fetch(scopeBase(scope), { headers: headers() });
  await checkOk(r);
  return (await r.json()) as ScopeOut;
}

export async function getScopeMetrics(scope: string): Promise<ScopeMetrics> {
  const r = await fetch(`${scopeBase(scope)}/metrics`, { headers: headers() });
  await checkOk(r);
  return (await r.json()) as ScopeMetrics;
}

/**
 * Patch a scope's config. Unlike the old resource-level PATCH this MERGES —
 * send only the fields you are changing, not the whole config.
 */
export async function updateScopeConfig(
  scope: string,
  patch: KnowledgeConfigPatch,
): Promise<ScopeOut> {
  const r = await fetch(scopeBase(scope), {
    method: "PATCH",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  await checkOk(r);
  return (await r.json()) as ScopeOut;
}

/** Set or clear a scope's display label; null / "" reverts to the derived name. */
export async function renameScope(scope: string, label: string | null): Promise<ScopeOut> {
  const r = await fetch(`${scopeBase(scope)}/label`, {
    method: "PATCH",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify({ label }),
  });
  await checkOk(r);
  return (await r.json()) as ScopeOut;
}

// --- entries ----------------------------------------------------------------

export async function listEntries(scope: string, limit = 50, offset = 0): Promise<EntryListOut> {
  const r = await fetch(`${scopeBase(scope)}/entries?limit=${limit}&offset=${offset}`, {
    headers: headers(),
  });
  await checkOk(r);
  return (await r.json()) as EntryListOut;
}

export async function getEntry(scope: string, entryId: string): Promise<EntryOut> {
  const r = await fetch(`${scopeBase(scope)}/entries/${enc(entryId)}`, { headers: headers() });
  await checkOk(r);
  return (await r.json()) as EntryOut;
}

export async function addEntry(scope: string, input: EntryInput): Promise<EntryOut> {
  const r = await fetch(`${scopeBase(scope)}/entries`, {
    method: "POST",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  await checkOk(r);
  return (await r.json()) as EntryOut;
}

export async function deleteEntry(scope: string, entryId: string): Promise<void> {
  const r = await fetch(`${scopeBase(scope)}/entries/${enc(entryId)}`, {
    method: "DELETE",
    headers: headers(),
  });
  await checkOk(r);
}

export async function clearEntries(scope: string): Promise<number> {
  const r = await fetch(`${scopeBase(scope)}/entries`, { method: "DELETE", headers: headers() });
  await checkOk(r);
  const data = (await r.json()) as { cleared: number };
  return data.cleared;
}

// --- tidy -------------------------------------------------------------------

/**
 * Run the tidy pass over the scope's notes NOW (the manual trigger for the
 * pass the NotesTidyWorker otherwise runs on a timer). The route is the
 * long-standing `POST /knowledge/{scope}/organize`. Only `status` is read
 * here — a pass with no internal model configured returns a clean no-op
 * status rather than an error.
 */
export async function tidyScope(scope: string): Promise<TidyOut> {
  const r = await fetch(`${scopeBase(scope)}/organize`, { method: "POST", headers: headers() });
  await checkOk(r);
  return (await r.json()) as TidyOut;
}
