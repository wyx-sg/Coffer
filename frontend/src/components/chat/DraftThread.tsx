// src/components/chat/DraftThread.tsx
// The blank "new chat" surface shown before a conversation exists (the draft).
// Chat talks only to Coffer-managed agents (Claude Code / Codex); sending the
// first message is what actually creates the conversation (see
// useChatController.sendDraft). The turn runs in the Coffer-managed workspace
// (~/.coffer/workspace) by default — there is no per-turn working-directory
// picker. When no managed agent is available, an install/configure empty state
// is shown instead.
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Bot, MessageSquareOff } from "lucide-react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { AgentInfo } from "@/lib/api/chat";
import { WIRE_BY_AGENT } from "@/lib/api/providers";
import { useProviders } from "@/lib/hooks/useProviders";
import { Composer } from "./Composer";
import { ModelPicker } from "./ModelPicker";

interface Props {
  agents: AgentInfo[];
  agentKey: string;
  /** True when no Coffer-managed agent is available (shows an empty state). */
  noManagedAgent?: boolean;
  onAgentChange: (agentKey: string) => void;
  /** The chosen per-conversation model for the new conversation (null = default). */
  modelValue?: string | null;
  onModelChange?: (model: string | null) => void;
  onSend: (text: string) => void;
  /** True while the create-then-send round-trip is in flight. */
  creating?: boolean;
}

export function DraftThread({
  agents,
  agentKey,
  noManagedAgent = false,
  onAgentChange,
  modelValue = null,
  onModelChange,
  onSend,
  creating = false,
}: Props) {
  const { t } = useTranslation();
  const agentName = agents.find((a) => a.agent_key === agentKey)?.display_name ?? agentKey;

  // Whether the selected agent has an active LLM connection for its wire. With
  // none configured the agent has no model to talk to, so we surface an
  // actionable empty state linking to Settings → LLM Connections rather than a
  // composer that would only 409 on send.
  const providers = useProviders();
  const wire = WIRE_BY_AGENT[agentKey];
  const hasConnection = useMemo(
    () => (providers.data ?? []).some((p) => p.wire_format === wire && p.is_active),
    [providers.data, wire],
  );
  // Until the providers query settles we don't yet know whether a connection
  // exists. Render the composer optimistically rather than flashing the
  // "no connection" empty state on first paint (it would only flip back once
  // the query resolves). The empty state shows only once we KNOW there's none.
  const showNoConnection = !providers.isPending && !hasConnection;

  // No Coffer-managed agent on PATH / registered — there is nothing to chat
  // with, so guide the user to install or configure one.
  if (noManagedAgent) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 p-12 text-center">
        <MessageSquareOff
          className="size-12 text-muted-foreground/40"
          strokeWidth={1.25}
          aria-hidden
        />
        <div className="space-y-1">
          <h2 className="text-lg font-semibold">{t("chat.draft.noAgentTitle")}</h2>
          <p className="max-w-sm text-sm text-muted-foreground">{t("chat.draft.noAgentBody")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Top bar: the agent, chosen before the first message rather than in a modal. */}
      <div className="flex items-center gap-3 border-b border-border bg-card/50 px-4 py-2">
        <div className="flex items-center gap-1.5">
          <Bot className="size-4 shrink-0 text-primary" strokeWidth={1.75} />
          <Select value={agentKey} onValueChange={onAgentChange}>
            <SelectTrigger
              className="h-7 w-48 border-none bg-transparent px-1 text-sm font-medium shadow-none"
              aria-label={t("chat.newConversation.agent")}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {agents.map((a) => (
                <SelectItem key={a.agent_key} value={a.agent_key} disabled={!a.available}>
                  {a.display_name}
                  {a.available ? "" : ` (${t("chat.newConversation.unavailable")})`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {/* Optional model for the new conversation, beside the agent picker. */}
        {hasConnection && (
          <ModelPicker
            agentKey={agentKey}
            value={modelValue}
            onCommit={(model) => onModelChange?.(model)}
          />
        )}
      </div>

      {!showNoConnection ? (
        <>
          <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
            <Bot className="mb-3 size-8 text-primary/70" strokeWidth={1.5} />
            <p className="text-sm text-muted-foreground">
              {t("chat.draft.guide", { agent: agentName })}
            </p>
          </div>
          <Composer onSend={onSend} disabled={creating} />
        </>
      ) : (
        // No active LLM connection for this agent's wire → actionable empty
        // state instead of a composer that would only fail on send.
        <div className="flex flex-1 flex-col items-center justify-center gap-4 p-12 text-center">
          <MessageSquareOff
            className="size-12 text-muted-foreground/40"
            strokeWidth={1.25}
            aria-hidden
          />
          <div className="space-y-1">
            <h2 className="text-lg font-semibold">{t("chat.draft.noConnectionTitle")}</h2>
            <p className="max-w-sm text-sm text-muted-foreground">
              {t("chat.draft.noConnectionBody")}
            </p>
          </div>
          <Link
            to="/settings/llm-connections"
            className="text-sm font-medium text-primary underline-offset-4 hover:underline"
          >
            {t("chat.draft.noConnectionCta")}
          </Link>
        </div>
      )}
    </div>
  );
}
