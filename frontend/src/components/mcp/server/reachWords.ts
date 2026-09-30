// src/components/mcp/server/reachWords.ts — a server's reach in words, for the pane's facts and its callouts.
import type { TFunction } from "i18next";

import type { AgentOut } from "@/lib/api/agents";
import type { ResourceOut } from "@/lib/api/resources";

/** The agents a server reaches now (none while it is off). */
export function reachedAgents(resource: ResourceOut, agents: readonly AgentOut[]): AgentOut[] {
  if (!resource.enabled) return [];
  const scoped = resource.scope?.agents ?? null;
  return scoped === null ? [...agents] : agents.filter((a) => scoped.includes(a.uid));
}

/** "All agents", "Claude Code, Codex", "No agent selected", or "Off — kept: …". */
export function reachWords(
  t: TFunction,
  resource: ResourceOut,
  agents: readonly AgentOut[],
): string {
  const scoped = resource.scope?.agents ?? null;
  const chosen = scoped === null ? agents : agents.filter((a) => scoped.includes(a.uid));
  const names = chosen.map((a) => a.display_name).join(", ");
  if (!resource.enabled) {
    return names ? t("mcp.page.offKept", { agents: names }) : t("skills.offMark");
  }
  if (scoped === null) return t("agentBadge.allAgents");
  return names || t("scope.noneSelected");
}
