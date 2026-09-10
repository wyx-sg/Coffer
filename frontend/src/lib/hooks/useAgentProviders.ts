// frontend/src/lib/hooks/useAgentProviders.ts — TanStack Query binding for the
// turn platform's agent registry (GET /api/v1/agent-providers).
import { useQuery } from "@tanstack/react-query";

import { agentProvidersApi } from "@/lib/api/agentProviders";

/** The agents a channel can be bound to. */
export function useAgentProviders() {
  return useQuery({
    queryKey: ["agent-providers"],
    queryFn: async () => (await agentProvidersApi.list()).agents,
  });
}
