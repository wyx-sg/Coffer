// frontend/src/lib/hooks/useAgentPending.ts — what long work is running on one agent right now.
//
// Connecting, disconnecting and adding an agent write the
// agent's own config files and can take seconds. The mutations that do it are
// keyed, so the row's status cell, its action button and the detail header all
// read the same pending state wherever the work was started from, and show a
// transition instead of an unchanged row.
import { useMutationState } from "@tanstack/react-query";

import { AGENT_REGISTER_KEY, agentConnectMutationKey } from "@/lib/hooks/useAgents";

export type AgentPending = "adding" | "connecting" | "disconnecting";

function usePendingVars<T>(mutationKey: readonly string[]): T[] {
  return useMutationState({
    filters: { mutationKey, status: "pending" },
    select: (m) => m.state.variables as T,
  });
}

export function useAgentPending(row: { uid: string | null; type: string }): AgentPending | null {
  const uid = row.uid ?? "";
  const connecting = usePendingVars<boolean>(agentConnectMutationKey(uid));
  const registering = usePendingVars<{ type: string }>(AGENT_REGISTER_KEY);
  if (uid && connecting.length > 0) return connecting[0] ? "connecting" : "disconnecting";
  if (registering.some((v) => v.type === row.type)) return "adding";
  return null;
}
