// frontend/src/lib/hooks/useAgentModels.ts — TanStack Query binding for an
// agent's model catalogue (/agent-providers/{key}/models).
//
// The catalogue is what the agent can actually run on its own login. It is
// server-owned rather than a frontend constant, so the chat model picker and
// the channel's model fields both read it here instead of hardcoding tiers that
// drift. Nothing narrows it — a surface that must offer less (a channel's
// allowed range, spec channels FR-071) applies its own range over this list.
import { useQuery } from "@tanstack/react-query";

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
