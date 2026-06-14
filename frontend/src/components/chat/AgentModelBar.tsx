// components/chat/AgentModelBar.tsx
// Top bar in the message thread: shows which Coffer-managed agent the
// conversation is bound to (Claude Code / Codex). Managed agents carry no
// Coffer-registered model, so there is no model selector here.
import { Bot } from "lucide-react";

interface Props {
  /** Display name of the conversation's agent, from the agents API. */
  agentLabel?: string;
}

export function AgentModelBar({ agentLabel }: Props) {
  return (
    <div className="flex items-center gap-3 border-b border-border bg-card/50 px-4 py-2">
      {/* Agent label — sourced from the registry via the agents API. */}
      <div className="flex items-center gap-1.5 text-sm font-medium text-foreground">
        <Bot className="size-4 shrink-0 text-primary" strokeWidth={1.75} />
        <span>{agentLabel}</span>
      </div>
    </div>
  );
}
