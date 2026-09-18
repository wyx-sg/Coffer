// frontend/src/lib/hooks/useScope.ts
//
// TanStack Query bindings over `lib/api/scope.ts` for the generic per-agent
// activation scope (ADR per-agent-resource-scope). The requests themselves live
// in the api module, because the bulk reach bar needs them without a hook.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { agentsKey, ownListKeyForKind, resourceScopeKey, resourcesKey } from "@/lib/api/queryKeys";
import { scopeApi, type ResourceScope, type Scope } from "@/lib/api/scope";
import { useToast } from "@/components/ui/toast";

/**
 * The scope shape itself (`{agents}`, `null` = unrestricted, `[]` = matches
 * nothing) is declared once in `lib/api/scope.ts` against the generated
 * `ScopeOut`, and re-exported here so components keep importing their scope
 * types from the hook module.
 */
export type { ResourceScope, Scope };

/**
 * Current activation scope for one resource, plus whether its kind supports
 * scope.
 *
 * `enabled: false` turns the query off for callers that already hold the
 * answer — the list payloads (`ResourceOut.scope`, `SkillOut.scope`) carry it,
 * so a table rendering one ScopeControl per row must not pay one GET per row.
 */
export function useResourceScope(uid: string, enabled = true) {
  return useQuery({
    queryKey: resourceScopeKey(uid),
    queryFn: () => scopeApi.get(uid),
    enabled: enabled && uid.length > 0,
  });
}

/**
 * Replace a resource's activation scope (`null` clears it back to unscoped —
 * active for every agent). A scope change flips what the gateway exposes and
 * what skill delivery reconciles, so the agent-facing lists are invalidated
 * alongside the scope itself.
 *
 * The write takes the uid alone. `kind` is here only to pick the kind's own
 * list key to refresh afterwards — the same reason `useResourceMutations`
 * carries it.
 */
export function useUpdateResourceScope(kind: string, uid: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (scope: Scope | null) => scopeApi.put(uid, scope),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: resourceScopeKey(uid) });
      void qc.invalidateQueries({ queryKey: agentsKey });
      // The list payloads carry `scope`, and the list tables now render the
      // control from that field rather than from this query — so a write here
      // has to refresh them too, or a row would keep showing its pre-write
      // reach. The kind's own list key is the same rule useResourceMutations
      // applies (`ownListKeyForKind`).
      void qc.invalidateQueries({ queryKey: resourcesKey });
      const own = ownListKeyForKind(kind);
      if (own) void qc.invalidateQueries({ queryKey: own });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
