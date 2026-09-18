// frontend/src/lib/api/scope.ts
//
// Request functions for the framework-level per-agent activation scope
// (ADR per-agent-resource-scope): GET/PUT /resources/{uid}/scope, served by
// resource_routes.py for every kind rather than by a per-kind endpoint.
// Hand-written like the sibling modules, because the generated client does not
// cover these sub-routes; transport via the shared `call` (.agents/frontend.md §4).
//
// They live here rather than inside useScope.ts because the bulk reach bar
// writes scope for a whole selection through useBulkMutate, which takes a plain
// promise-returning function, never a toasting mutation hook (one summary toast,
// not one per row).
import { call, enc } from "@/lib/api/call";
import type { components } from "@/lib/api/types";

/**
 * A resource's activation scope: the allow-list of agents it reaches.
 *
 * `null` is unrestricted; `[]` matches nothing, i.e. dormant. The whole scope
 * being `null` (see `ResourceScope.scope`) means active for every agent.
 *
 * `agents` holds agent UIDS, not agent names: a scope is a stored pointer at
 * another resource, and a name is a label its owner may change. A picker
 * therefore offers names, sends uids, and renders stored uids back as names —
 * never the other way round.
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

function scopePath(uid: string): string {
  return `/resources/${enc(uid)}/scope`;
}

export const scopeApi = {
  get: (uid: string): Promise<ResourceScope> => call<ResourceScope>(scopePath(uid)),

  /** Replace the scope; `null` clears it back to unscoped — every agent. */
  put: (uid: string, scope: Scope | null): Promise<ResourceOut> =>
    call<ResourceOut>(scopePath(uid), { method: "PUT", body: { scope } }),
};
