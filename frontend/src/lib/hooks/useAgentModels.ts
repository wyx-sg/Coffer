// frontend/src/lib/hooks/useAgentModels.ts — TanStack Query binding for an
// agent's model catalogue (/agent-providers/{key}/models).
//
// The pages read only the agent's default model from it (the Agents list and the
// Overview's Model section); the daemon narrows the catalogue once, so this hook
// adds nothing to the answer.
import { useQuery } from "@tanstack/react-query";

import { agentModelsApi, type AgentModelsOut } from "@/lib/api/agentModels";
import { agentBuiltinModelsKey, agentProviderModelsKey } from "@/lib/api/queryKeys";

function useAgentModelsResponse<T>(agentKey: string, select: (r: AgentModelsOut) => T) {
  return useQuery<AgentModelsOut, Error, T>({
    queryKey: agentProviderModelsKey(agentKey),
    queryFn: () => agentModelsApi.list(agentKey),
    select,
    // An empty key would 404 the endpoint.
    enabled: agentKey !== "",
  });
}

/** The model the agent's own config names as its default; null when it names none. */
export function useAgentDefaultModel(agentKey: string) {
  return useAgentModelsResponse<string | null>(agentKey, (r) => r.default_model ?? null);
}

/** The name of the model the agent's own login runs when its config names none, when the agent
 *  itself reports it (Codex); null when it does not (Claude Code decides by account at turn time). */
export function useAgentBuiltinDefault(agentKey: string) {
  return useAgentModelsResponse<string | null>(agentKey, (r) =>
    r.builtin_default ? r.builtin_default.label || r.builtin_default.id : null,
  );
}

/** The model a turn with no override runs on (the config's model, else the reported built-in
 *  default), by its name where the catalogue gives one; null when Coffer cannot know it. */
export function useAgentResolvedDefault(agentKey: string) {
  return useAgentModelsResponse<string | null>(agentKey, (r) => {
    const id = r.resolved_default ?? null;
    if (!id) return null;
    const named =
      r.models.find((m) => m.id === id) ??
      (r.builtin_default?.id === id ? r.builtin_default : null);
    return named?.label || id;
  });
}

/** The models the agent's OWN login offers (not the active connection's), for the
 *  Change model dialog's built-in Model select. Fetched only when asked for. */
export function useBuiltinModels(agentKey: string, enabled: boolean) {
  return useQuery<AgentModelsOut>({
    queryKey: agentBuiltinModelsKey(agentKey),
    queryFn: () => agentModelsApi.list(agentKey, "builtin"),
    enabled: enabled && agentKey !== "",
  });
}
