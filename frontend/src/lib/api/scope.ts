// frontend/src/lib/api/scope.ts
//
// Request functions for the framework-level per-agent activation scope
// (ADR per-agent-resource-scope): GET/PUT /resources/{kind}/{name}/scope, served
// by resource_routes.py for every kind rather than by a per-kind endpoint.
// Hand-written like the sibling modules, because the generated client does not
// cover these sub-routes.
//
// They live here rather than inside useScope.ts because the bulk reach bar
// writes scope for a whole selection through useBulkMutate, which takes a plain
// promise-returning function, never a toasting mutation hook (one summary toast,
// not one per row).
import { getCofferBaseUrl, getCofferToken } from "@/lib/auth";
import { ApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";

/**
 * A resource's activation scope: the allow-list of agents it reaches.
 *
 * `null` is unrestricted; `[]` matches nothing, i.e. dormant. The whole scope
 * being `null` (see `ResourceScope.scope`) means active for every agent.
 *
 * Scope is MACHINE-LOCAL, like the `enabled` flag it sits beside: this vault
 * holds it and never converges it with a remote, so it names agents and
 * nothing else — the machine is always the one asking.
 *
 * Structurally the generated `ScopeOut`, and deliberately declared against it:
 * this module is hand-written, so the alias is the one thing that does fail at
 * compile time if the shape ever drifts from the API.
 */
export type Scope = NonNullable<components["schemas"]["ScopeOut"]>;

/**
 * GET .../scope response: the current scope (`null` = unscoped, active for
 * every agent) plus whether this kind supports scope at all.
 *
 * Field names here MUST match `ResourceScopeOut` in
 * `backend/coffer/surfaces/http/schemas.py` — these sub-routes are hand-written
 * (the generated client does not cover them), so nothing checks this at compile
 * time. `resourceScopeContract` in useScope.test is the regression guard.
 */
export interface ResourceScope {
  scope: Scope | null;
  supports_scope: boolean;
}

type ResourceOut = components["schemas"]["ResourceOut"];

function headers(extra: HeadersInit = {}): HeadersInit {
  return { "X-Coffer-Token": getCofferToken() ?? "", "X-Coffer-Actor": "ui", ...extra };
}

async function checkOk(r: Response): Promise<Response> {
  if (!r.ok) {
    const data = (await r.json().catch(() => null)) as {
      error?: { code?: string; message?: string; details?: unknown };
    } | null;
    throw new ApiError(
      data?.error?.code ?? "INTERNAL_ERROR",
      data?.error?.message ?? `request failed: ${r.status}`,
      data?.error?.details,
    );
  }
  return r;
}

export function scopePath(kind: string, name: string): string {
  return `/resources/${encodeURIComponent(kind)}/${encodeURIComponent(name)}/scope`;
}

export const scopeApi = {
  async get(kind: string, name: string): Promise<ResourceScope> {
    const r = await fetch(`${getCofferBaseUrl()}${scopePath(kind, name)}`, { headers: headers() });
    await checkOk(r);
    return (await r.json()) as ResourceScope;
  },

  /** Replace the scope; `null` clears it back to unscoped — every agent. */
  async put(kind: string, name: string, scope: Scope | null): Promise<ResourceOut> {
    const r = await fetch(`${getCofferBaseUrl()}${scopePath(kind, name)}`, {
      method: "PUT",
      headers: { ...headers(), "Content-Type": "application/json" },
      body: JSON.stringify({ scope }),
    });
    await checkOk(r);
    return (await r.json()) as ResourceOut;
  },
};
