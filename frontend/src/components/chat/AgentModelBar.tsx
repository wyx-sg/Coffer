// components/chat/AgentModelBar.tsx
// The agent / model / effort cluster at the right of an open conversation's
// header: which Coffer-managed agent the conversation is bound to (Claude Code /
// Codex, by its mark), plus a per-conversation model picker. The
// picker sets agent_config.model — the agent's own model, passed through to its
// CLI (the coffer-model-is-an-internal-engine and provider-switching
// ADRs), mirroring the channel `/model` command. An empty
// value inherits the active provider profile's projected default. Beside it,
// for the agents whose models take one, the reasoning effort that model runs
// at; it renders nothing for the agents that have no such setting.
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useAgentConfig, useSetAgentEffort, useSetAgentModel } from "@/lib/hooks/useConversations";
import { EffortPicker } from "./EffortPicker";
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
  const { t } = useTranslation();
  const agentConfig = useAgentConfig(conversationId);
  const setModel = useSetAgentModel();
  const setEffort = useSetAgentEffort();

  return (
    <div className="flex shrink-0 items-center gap-2">
      {/* The agent a conversation talks to is fixed at its creation — its
          tooltip says so; the model and the effort switch here, as `/model`
          does in a channel. */}
      <TooltipProvider delayDuration={300}>
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              tabIndex={0}
              data-testid="conversation-agent"
              className="rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
            >
              <AgentBadge
                type={agentKey}
                name={agentLabel}
                size="sm"
                showName
                tooltip={false}
                className="px-1 text-xs font-medium text-text-muted"
              />
            </span>
          </TooltipTrigger>
          <TooltipContent>{t("conversations.header.agentFixed")}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <ModelPicker
        agentKey={agentKey}
        value={agentConfig.data?.model ?? null}
        disabled={disabled}
        onCommit={(model) => setModel.mutate({ id: conversationId, model })}
      />
      <EffortPicker
        agentKey={agentKey}
        model={agentConfig.data?.model ?? null}
        value={agentConfig.data?.effort ?? null}
        disabled={disabled}
        onCommit={(effort) => setEffort.mutate({ id: conversationId, effort })}
      />
    </div>
  );
}
