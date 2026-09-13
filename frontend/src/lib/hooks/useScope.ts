// frontend/src/lib/hooks/useScope.ts
//
// TanStack Query bindings over `lib/api/scope.ts` for the generic per-agent
// activation scope (ADR per-agent-resource-scope). The requests themselves live
// in the api module, because the bulk reach bar needs them without a hook.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { scopeApi, type ResourceScope, type Scope } from "@/lib/api/scope";
import { useToast } from "@/components/ui/toast";

/**
 * Active everywhere on both axes — what "Restricted" starts from, and what a
 * fully-relaxed selection normalises back to (`null` on the wire).
 *
 * The shape itself (`{agents, machines}`, `null` on an axis = unrestricted,
 * `[]` = matches nothing) is declared once in `lib/api/scope.ts` against the
 * generated `ScopeOut`, and re-exported here so components keep importing
 * their scope types from the hook module.
 */
export const UNRESTRICTED: Scope = { agents: null, machines: null };

export type { ResourceScope, Scope };

export function resourceScopeKey(kind: string, name: string) {
  return ["scope", kind, name] as const;
}

/** Kinds read through their OWN query key rather than the generic resource
 *  list; a scope write has to refresh those too. Mirrors the identically-named
 *  map in useResourceMutations.ts — keep the two in step. */
const KIND_QUERY_KEY: Record<string, string> = {
  skill: "skills",
  provider: "providers",
  agent: "agents",
};

/**
 * Current activation scope for one resource, plus whether its kind supports
 * scope.
 *
 * `enabled: false` turns the query off for callers that already hold the
 * answer — the list payloads (`ResourceOut.scope`, `SkillOut.scope`) carry it,
 * so a table rendering one ScopeControl per row must not pay one GET per row.
 */
export function useResourceScope(kind: string, name: string, enabled = true) {
  return useQuery({
    queryKey: resourceScopeKey(kind, name),
    queryFn: () => scopeApi.get(kind, name),
    enabled: enabled && name.length > 0,
  });
}

/**
 * Replace a resource's activation scope (`null` clears it back to unscoped —
 * active for every agent). A scope change flips what the gateway exposes and
 * what skill delivery reconciles, so the agent-facing lists are invalidated
 * alongside the scope itself.
 */
export function useUpdateResourceScope(kind: string, name: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (scope: Scope | null) => scopeApi.put(kind, name, scope),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: resourceScopeKey(kind, name) });
      void qc.invalidateQueries({ queryKey: ["agents"] });
      // The list payloads carry `scope`, and the list tables now render the
      // control from that field rather than from this query — so a write here
      // has to refresh them too, or a row would keep showing its pre-write
      // reach. The kind-own keys mirror useResourceMutations' rule.
      void qc.invalidateQueries({ queryKey: ["resources"] });
      const own = KIND_QUERY_KEY[kind];
      if (own) void qc.invalidateQueries({ queryKey: [own] });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
