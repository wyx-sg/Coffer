// src/components/mcp/server/reachWords.ts — the agents a server reaches, for the pane's callouts and dialogs.
import type { AgentOut } from "@/lib/api/agents";
import type { ResourceOut } from "@/lib/api/resources";

/** The agents a server reaches now (none while it is off). */
export function reachedAgents(resource: ResourceOut, agents: readonly AgentOut[]): AgentOut[] {
  if (!resource.enabled) return [];
  const scoped = resource.scope?.agents ?? null;
  return scoped === null ? [...agents] : agents.filter((a) => scoped.includes(a.uid));
}
