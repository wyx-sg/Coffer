// src/components/agent/agentMarkKind.ts — which official mark an agent type key is drawn with.

export type AgentMarkKind =
  | "claude-spark"
  | "openai-blossom"
  | "cursor"
  | "opencode"
  | "deepseek"
  | "antigravity"
  | "generic";

const KIND: Record<string, AgentMarkKind> = {
  claude_code: "claude-spark",
  codex: "openai-blossom",
  cursor: "cursor",
  opencode: "opencode",
  deepseek_harness: "deepseek",
  antigravity: "antigravity",
};

/** Which mark an agent type key is drawn with. */
export function agentMarkKind(type: string): AgentMarkKind {
  return KIND[type] ?? "generic";
}
