// frontend/src/lib/hooks/useChatAgents.ts — TanStack Query binding for the
// chat platform's agent registry (GET /api/v1/chat/agents).
import { useQuery } from "@tanstack/react-query";

import { chatApi } from "@/lib/api/chat";

/** The agents the chat platform offers, for the new-conversation picker. */
export function useChatAgents() {
  return useQuery({
    queryKey: ["chat-agents"],
    queryFn: async () => (await chatApi.listAgents()).agents,
  });
}
