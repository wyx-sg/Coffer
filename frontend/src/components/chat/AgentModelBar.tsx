// components/chat/AgentModelBar.tsx
// The agent / model cluster at the right of an open conversation's
// reply box toolbar: which Coffer-managed agent the conversation is bound to (Claude Code /
// Codex, by its mark), plus a per-conversation model picker. The
// picker sets agent_config.model — the agent's own model, passed through to its
// CLI (the model-catalogue-read-from-the-agent and provider-switching
// ADRs), mirroring the channel `/model` command. An empty
// value inherits the active provider profile's projected default.
import { AgentBadge } from "@/components/agent/AgentBadge";
import { useAgentConfig, useSetAgentModel } from "@/lib/hooks/useConversations";
import { ModelPicker } from "./ModelPicker";

interface Props {
  conversationId: string;
  /** The conversation's agent_key (drives the model suggestions). */
  agentKey: string;
  /** Display name of the conversation's agent, from the agents API. */
  agentLabel?: string;
  /** Archived/read-only conversation — the pickers are disabled. */
  disabled?: boolean;
}

export function AgentModelBar({ conversationId, agentKey, agentLabel, disabled = false }: Props) {
  const agentConfig = useAgentConfig(conversationId);
  const setModel = useSetAgentModel();

  return (
    <div className="flex shrink-0 items-center gap-2">
      {/* The agent is fixed at creation: a plain label, no control, nothing to
          explain. The model switches here, as `/model` does in a channel. */}
      <span
        data-testid="conversation-agent"
        className="inline-flex items-center px-1 text-xs font-medium text-text-muted"
      >
        <AgentBadge type={agentKey} name={agentLabel} size="sm" showName tooltip={false} />
      </span>
      <ModelPicker
        agentKey={agentKey}
        value={agentConfig.data?.model ?? null}
        disabled={disabled}
        onCommit={(model) => setModel.mutate({ id: conversationId, model })}
      />
    </div>
  );
}
