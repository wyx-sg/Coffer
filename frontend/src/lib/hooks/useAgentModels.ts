// frontend/src/lib/hooks/useAgentModels.ts — TanStack Query binding for an
// agent's model catalogue (/chat/agents/{key}/models).
//
// The catalogue is what the agent can actually run on its own login. It is
// server-owned rather than a frontend constant, so the chat model picker and the
// Agent page both read it here instead of hardcoding tiers that drift.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { agentModelsApi, type AgentModel } from "@/lib/api/agentModels";

/** Hierarchical key so a future per-agent invalidation catches the subtree. */
export const agentModelsKey = (agentKey: string) => ["agent-models", agentKey] as const;

export function useAgentModels(agentKey: string) {
  return useQuery<AgentModel[]>({
    queryKey: agentModelsKey(agentKey),
    queryFn: async () => (await agentModelsApi.list(agentKey)).models,
    // The draft agent selector can render before an agent is chosen; an empty
    // key would 404 the endpoint.
    enabled: agentKey !== "",
  });
}

/**
 * Which of the catalogue the user ticked as actually runnable.
 *
 * Kept apart from the catalogue on purpose: the curation UI renders every model
 * the agent reports and ticks this set against it, so the two have to arrive
 * separately. An empty array means "not curated yet" — every model is offered —
 * and never "no models".
 */
export const agentModelSelectionKey = (agentKey: string) =>
  ["agent-models", agentKey, "selection"] as const;

export function useAgentModelSelection(agentKey: string) {
  return useQuery<string[]>({
    queryKey: agentModelSelectionKey(agentKey),
    queryFn: async () => (await agentModelsApi.selection(agentKey)).models,
    enabled: agentKey !== "",
  });
}

/** Replace the curated set. `[]` clears it, restoring the whole catalogue. */
export function useSetAgentModelSelection(agentKey: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (models: string[]) => agentModelsApi.setSelection(agentKey, models),
    onSuccess: (out) => {
      // Seed the answer the server just confirmed, then invalidate the whole
      // subtree: the selection key sits under the catalogue key, so one call
      // refreshes every picker reading either.
      qc.setQueryData(agentModelSelectionKey(agentKey), out.models);
      qc.invalidateQueries({ queryKey: agentModelsKey(agentKey) });
    },
  });
}
