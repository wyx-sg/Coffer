// frontend/src/lib/api/scope.ts
//
// Request functions for the framework-level per-agent activation scope
// (ADR per-agent-resource-scope): GET/PUT /resources/{uid}/scope, served by
// resource_routes.py for every kind rather than by a per-kind endpoint.
// Transport via the typed client (.agents/frontend.md §4).
//
// They live here rather than inside useScope.ts because the bulk reach bar
// writes scope for a whole selection through useBulkMutate, which takes a plain
// promise-returning function, never a toasting mutation hook (one summary toast,
// not one per row).
import { getApiClient, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/types";
import type { components as ResourceFrameworkWire } from "@/lib/api/generated/resource-framework";

/**
 * A resource's activation scope: the allow-list of agents it reaches.
 *
 * `null` is unrestricted; a list names at least one agent (`[]` is refused —
 * a resource that reaches nobody is switched off). The whole scope
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
 * The generated `ScopeOut`.
 */
export type Scope = NonNullable<components["schemas"]["ScopeOut"]>;

/**
 * GET .../scope response: the current scope (`null` = unscoped, active for
 * every agent) plus whether this kind supports scope at all.
 */
export type ResourceScope = ResourceFrameworkWire["schemas"]["ResourceScopeOut"];

type ResourceOut = components["schemas"]["ResourceOut"];

export const scopeApi = {
  get: (uid: string): Promise<ResourceScope> =>
    unwrap(getApiClient().GET("/resources/{uid}/scope", { params: { path: { uid } } })),

  /** Replace the scope; `null` clears it back to unscoped — every agent. */
  put: (uid: string, scope: Scope | null): Promise<ResourceOut> =>
    unwrap(
      getApiClient().PUT("/resources/{uid}/scope", { params: { path: { uid } }, body: { scope } }),
    ),
};
