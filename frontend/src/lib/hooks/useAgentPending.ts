// frontend/src/lib/hooks/useAgentPending.ts — what long work is running on one agent right now.
//
// Connecting, disconnecting, enabling, disabling and adding an agent write the
// agent's own config files and can take seconds. The mutations that do it are
// keyed, so the row's status cell, its action button and the detail header all
// read the same pending state wherever the work was started from, and show a
// transition instead of an unchanged row.
import { useMutationState } from "@tanstack/react-query";

import { AGENT_REGISTER_KEY, agentConnectMutationKey } from "@/lib/hooks/useAgents";
import { DISABLE_KEY, ENABLE_KEY } from "@/lib/hooks/useResourceMutations";

export type AgentPending = "adding" | "connecting" | "disconnecting" | "enabling" | "disabling";

function usePendingVars<T>(mutationKey: readonly string[]): T[] {
  return useMutationState({
    filters: { mutationKey, status: "pending" },
    select: (m) => m.state.variables as T,
  });
}

export function useAgentPending(row: { uid: string | null; type: string }): AgentPending | null {
  const uid = row.uid ?? "";
  const connecting = usePendingVars<boolean>(agentConnectMutationKey(uid));
  const enabling = usePendingVars<{ uid: string }>(ENABLE_KEY);
  const disabling = usePendingVars<{ uid: string }>(DISABLE_KEY);
  const registering = usePendingVars<{ type: string }>(AGENT_REGISTER_KEY);
  if (uid && connecting.length > 0) return connecting[0] ? "connecting" : "disconnecting";
  if (uid && enabling.some((v) => v.uid === uid)) return "enabling";
  if (uid && disabling.some((v) => v.uid === uid)) return "disabling";
  if (registering.some((v) => v.type === row.type)) return "adding";
  return null;
}
