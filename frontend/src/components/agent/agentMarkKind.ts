// src/components/agent/agentMarkKind.ts — which official mark an agent type key is drawn with.

export type AgentMarkKind = "claude-spark" | "openai-blossom" | "generic";

/** Which mark an agent type key is drawn with. */
export function agentMarkKind(type: string): AgentMarkKind {
  if (type === "claude_code") return "claude-spark";
  if (type === "codex") return "openai-blossom";
  return "generic";
}
