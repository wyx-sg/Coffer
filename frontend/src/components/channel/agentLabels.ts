// frontend/src/components/channel/agentLabels.ts
// The display name for a channel's bound agent. `default_agent` is a chat
// provider KEY (`claude_code`), which is what the turn resolves by and not
// something to put in front of a user. The live registry (useAgentProviders)
// carries each key's display name; the static map covers the same keys when
// the registry has not loaded yet, so the list never flashes raw keys.
import type { AgentProviderInfo } from "@/lib/api/agentProviders";

const STATIC_LABELS: Record<string, string> = {
  claude_code: "Claude Code",
  codex: "Codex",
};

/**
 * Display name for `agentKey`: the registry's, then the static map's, then
 * the key itself (an unknown or since-removed binding is still shown, so the
 * owner can see what to fix).
 */
export function agentDisplayName(agentKey: string, registry?: AgentProviderInfo[]): string {
  const live = registry?.find((a) => a.agent_key === agentKey)?.display_name;
  return live ?? STATIC_LABELS[agentKey] ?? agentKey;
}
