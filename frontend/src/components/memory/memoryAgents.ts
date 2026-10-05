// frontend/src/components/memory/memoryAgents.ts — which agents a memory was learned from, by name.
//
// A memory's provenance (`origins[]`) names each source by the agent's
// RESOURCE name (`claude-code`), the file it came from and when it was read.
// The partition page shows only the agents' product names (spec memory
// "Show a partition's memories read-only": no native paths, no original text),
// so this reduces the provenance to distinct agent types in Agents-page
// order. A resource name the registry does not know is shown as written.
import { sortAgents } from "@/components/agent/agentOrder";
import { agentTypeLabel } from "@/lib/agents/display";
import type { OriginOut } from "@/lib/api/memoryTypes";

/** `claude-code` / `claude_code` / `Claude-Code` → `claude_code`. */
export function agentTypeOfOrigin(agent: string): string {
  return agent.trim().toLowerCase().replace(/-/g, "_");
}

/** The distinct agents behind a memory, as product names, Claude Code first. */
export function learnedByLabels(origins: readonly Pick<OriginOut, "agent">[]): string[] {
  const seen: { type: string; raw: string }[] = [];
  for (const origin of origins) {
    const type = agentTypeOfOrigin(origin.agent);
    if (type && !seen.some((s) => s.type === type)) seen.push({ type, raw: origin.agent.trim() });
  }
  return sortAgents(seen).map((a) => {
    const label = agentTypeLabel(a.type);
    return label === a.type ? a.raw : label;
  });
}
