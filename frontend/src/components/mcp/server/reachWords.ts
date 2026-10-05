// src/components/mcp/server/reachWords.ts — the agents a server reaches, for the pane's callouts and dialogs.
import type { AgentOut } from "@/lib/api/agents";
import type { ResourceOut } from "@/lib/api/resources";
import { joinNames } from "@/lib/mcp/serverState";

/** The names of the agents turning a server on gives it to: `null` is every
 *  agent (an unscoped reach), otherwise the chosen ones registered here, joined
 *  for `lang`. Judged from the stored scope, so it answers for an off server too. */
export function namesOnTurnOn(
  resource: ResourceOut,
  agents: readonly AgentOut[],
  lang: string,
): string | null {
  const scoped = resource.scope?.agents ?? null;
  if (scoped === null) return null;
  const chosen = agents.filter((a) => scoped.includes(a.uid)).map((a) => a.display_name);
  return joinNames(chosen, lang);
}

/** The agents a server reaches now (none while it is off). */
export function reachedAgents(resource: ResourceOut, agents: readonly AgentOut[]): AgentOut[] {
  if (!resource.enabled) return [];
  const scoped = resource.scope?.agents ?? null;
  return scoped === null ? [...agents] : agents.filter((a) => scoped.includes(a.uid));
}
