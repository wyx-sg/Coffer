// components/chat/AgentModelBar.tsx
// Top bar in the message thread: which Coffer-managed agent the conversation is
// bound to (Claude Code / Codex), plus a per-conversation model picker. The
// picker sets agent_config.model — the agent's own model, passed through to its
// CLI (ADR-024 → ADR-032), mirroring the channel `/model` command. An empty
// value inherits the active provider profile's projected default.
import { Bot } from "lucide-react";

import { useAgentConfig, useSetAgentModel } from "@/lib/hooks/useConversations";
import { ModelPicker } from "./ModelPicker";

interface Props {
  conversationId: string;
  /** The conversation's agent_key (drives the model suggestions). */
  agentKey: string;
  /** Display name of the conversation's agent, from the agents API. */
  agentLabel?: string;
  /** Archived/read-only conversation — the model picker is disabled. */
  disabled?: boolean;
}

export function AgentModelBar({ conversationId, agentKey, agentLabel, disabled = false }: Props) {
  const agentConfig = useAgentConfig(conversationId);
  const setModel = useSetAgentModel();

  return (
    <div className="flex items-center gap-3 border-b border-border bg-card/50 px-4 py-2">
      {/* Agent label — sourced from the registry via the agents API. */}
      <div className="flex items-center gap-1.5 text-sm font-medium text-foreground">
        <Bot className="size-4 shrink-0 text-primary" strokeWidth={1.75} />
        <span>{agentLabel}</span>
      </div>
      <ModelPicker
        agentKey={agentKey}
        value={agentConfig.data?.model ?? null}
        disabled={disabled}
        onCommit={(model) => setModel.mutate({ id: conversationId, model })}
      />
    </div>
  );
}
