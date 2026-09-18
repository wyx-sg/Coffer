// frontend/src/components/channel/agentLabels.ts
// The display name for a channel's bound agent.
//
// `default_agent` holds an agent RESOURCE UID — the identity every
// cross-resource reference carries — which is not something to put in front of
// a user. This resolves it against the registered agents.
//
// It used to hold a chat provider KEY (`claude_code`) and needed a static map
// of keys to product names, because the key was a third vocabulary beside the
// resource's name and its uid. There is one vocabulary now: the uid, resolved
// through the agent list the rest of the app already reads.
//
// A uid nothing answers to falls back to the uid itself rather than to an empty
// cell: the binding really does point somewhere, and showing what it points at
// is the only thing that lets the owner fix it.
import type { AgentOut } from "@/lib/api/agents";

export function agentDisplayName(agentUid: string, agents?: AgentOut[]): string {
  return agents?.find((a) => a.uid === agentUid)?.name ?? agentUid;
}
