// frontend/src/kinds/knowledge/api.ts
//
// Hand-written fetch helpers for the one `knowledge` kind. The two former route
// trees (`/memory_stores/*` and `/knowledge_bases/*`) collapse into
// `/api/v1/knowledge/*` with the SCOPE name as the path segment.
//
// `global` and `project-<ULID>` auto-provision on first use; a named collection
// is created deliberately through POST /knowledge (which rejects the two
// auto-scope name shapes with 422). Entries are written directly — no LLM at
// write time. Document helpers live in ./document-api; both are re-exported
// here so call sites keep one import path.

import { checkOk, enc, headers, knowledgeRoot, scopeBase } from "./client";
import type {
  ConsolidationLogOut,
  EntryInput,
  EntryListOut,
  EntryOut,
  HandoffOut,
  KnowledgeConfigPatch,
  MergeOut,
  MergeScanOut,
  RecallResponse,
  RulesOut,
  ScopeListOut,
  ScopeMetrics,
  ScopeOut,
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

// --- lane read views --------------------------------------------------------
// Pure GET reads of the scope's curated lanes (no LLM, no mutation). Empty
// scopes still 200 with empty lists / null text.

export async function getKnowledgeRules(scope: string): Promise<RulesOut> {
  const r = await fetch(`${scopeBase(scope)}/rules`, { headers: headers() });
  await checkOk(r);
  return (await r.json()) as RulesOut;
}

export async function getKnowledgeHandoff(scope: string): Promise<HandoffOut> {
  const r = await fetch(`${scopeBase(scope)}/handoff`, { headers: headers() });
  await checkOk(r);
  return (await r.json()) as HandoffOut;
}

export async function getConsolidationLog(scope: string): Promise<ConsolidationLogOut> {
  const r = await fetch(`${scopeBase(scope)}/consolidation-log`, { headers: headers() });
  await checkOk(r);
  return (await r.json()) as ConsolidationLogOut;
}

// --- lane deletes -----------------------------------------------------------
// Each removes the file from disk; the backend appends one line to the
// consolidation log (except deleting the log itself), so callers also
// invalidate the changelog query key after a delete.

export async function deleteHandoffBranch(scope: string, branch: string): Promise<void> {
  const r = await fetch(`${scopeBase(scope)}/handoff/${enc(branch)}`, {
    method: "DELETE",
    headers: headers(),
  });
  await checkOk(r);
}

export async function deleteKnowledgeRules(scope: string): Promise<void> {
  const r = await fetch(`${scopeBase(scope)}/rules`, { method: "DELETE", headers: headers() });
  await checkOk(r);
}

export async function deleteConsolidationLog(scope: string): Promise<void> {
  const r = await fetch(`${scopeBase(scope)}/consolidation-log`, {
    method: "DELETE",
    headers: headers(),
  });
  await checkOk(r);
}

// --- recall (entries) -------------------------------------------------------

export async function recall(
  scope: string,
  query: string,
  opts: { topK?: number; scope?: "global" | "project" | "both" } = {},
): Promise<RecallResponse> {
  // External retrieval is "one query → one answer": the backend auto-selects
  // the strategy, so the request carries no `mode` and the response no longer
  // returns `mode`/`fallback`.
  const body: Record<string, unknown> = { query, top_k: opts.topK ?? 5 };
  if (opts.scope) body.scope = opts.scope;
  const r = await fetch(`${scopeBase(scope)}/recall`, {
    method: "POST",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await checkOk(r);
  return (await r.json()) as RecallResponse;
}

// --- AI-assisted scope merge ------------------------------------------------

/** Scan every pair of project scopes for same-project duplicates (read-only). */
export async function mergeScanScopes(): Promise<MergeScanOut> {
  const r = await fetch(`${knowledgeRoot()}/merge_scan`, { method: "POST", headers: headers() });
  await checkOk(r);
  return (await r.json()) as MergeScanOut;
}

/** Merge `source` into `target` (additive; the source scope is retired). */
export async function mergeScopes(
  source: string,
  target: string,
  opts: { organize?: boolean } = {},
): Promise<MergeOut> {
  const r = await fetch(`${knowledgeRoot()}/merge`, {
    method: "POST",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify({ source, target, organize: opts.organize ?? true }),
  });
  await checkOk(r);
  return (await r.json()) as MergeOut;
}
