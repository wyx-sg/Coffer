// src/components/chat/DraftThread.tsx
// The draft New conversation opens (`/conversations/new`): a header with the
// chosen agent, its model and effort and the folder it will work in, an empty
// thread, and the composer whose first send creates the conversation (see
// useChatController.sendDraft) — no welcome or suggestions. A hand-off opens it
// with a prompt already in the composer (`restore`), waiting for Send. When no managed
// agent is available, a state saying how to get one replaces the composer.
import { useTranslation } from "react-i18next";
import { Folder, MessageSquareOff } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { EmptyState } from "@/components/EmptyState";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { AgentProviderInfo } from "@/lib/api/agentProviders";
import type { ChatAttachment } from "@/lib/api/chat";
import { useAgentModels } from "@/lib/hooks/useAgentModels";
import type { ComposerRestore } from "@/lib/hooks/useComposerRestore";
import { Composer } from "./Composer";
import { EffortPicker } from "./EffortPicker";
import { ModelPicker } from "./ModelPicker";

interface Props {
  agents: AgentProviderInfo[];
  agentKey: string;
  /** The folder the turn will run in; null is Coffer's own workspace. */
  cwd?: string | null;
  /** True when no Coffer-managed agent is available (shows an empty state). */
  noManagedAgent?: boolean;
  onAgentChange: (agentKey: string) => void;
  modelValue?: string | null;
  onModelChange?: (model: string | null) => void;
  effortValue?: string | null;
  onEffortChange?: (effort: string | null) => void;
  /** Create the conversation and send; resolves whether the create succeeded. */
  onSend: (text: string, attachments: ChatAttachment[]) => void | Promise<boolean>;
  /** True while the create-then-send round-trip is in flight. */
  creating?: boolean;
  /** Text to type into the composer once (a hand-off's prompt); never sent by itself. */
  restore?: ComposerRestore | null;
  onRestored?: () => void;
}

export function DraftThread({
  agents,
  agentKey,
  cwd = null,
  noManagedAgent = false,
  onAgentChange,
  modelValue = null,
  onModelChange,
  effortValue = null,
  onEffortChange,
  onSend,
  creating = false,
  restore,
  onRestored,
}: Props) {
  const { t } = useTranslation();
  const agentName = agents.find((a) => a.agent_key === agentKey)?.display_name ?? agentKey;
  const models = useAgentModels(agentKey).data;
  const modelLabel = modelValue
    ? models?.find((m) => m.id === modelValue)?.label || modelValue
    : null;
  // What the first turn will run with — only the parts that were chosen; an
  // unset model or effort is the agent's own default, which it never names.
  const details = [
    cwd ? abbreviateHomePath(cwd) : t("conversations.draft.workspace"),
    modelLabel,
    effortValue ? t("conversations.draft.effort", { effort: effortValue }) : null,
  ]
    .filter(Boolean)
    .join(" · ");

  if (noManagedAgent) {
    return (
      <EmptyState
        className="flex-1"
        icon={MessageSquareOff}
        title={t("conversations.draft.noAgentTitle")}
        description={t("conversations.draft.noAgentBody")}
      />
    );
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex h-[52px] shrink-0 items-center gap-3 border-b border-border-subtle px-5">
        <h1 className="text-md font-semibold text-text">{t("conversations.new.title")}</h1>
        <span className="inline-flex min-w-0 items-center gap-1.5 text-xs text-text-muted">
          <Folder className="size-3.5 shrink-0" aria-hidden />
          <span className="truncate font-mono">{cwd ?? t("conversations.draft.workspace")}</span>
        </span>
        <span className="ml-auto" />
        <Select value={agentKey} onValueChange={onAgentChange}>
          <SelectTrigger
            className="h-control-sm w-auto gap-2 border-none bg-transparent px-1.5 text-xs font-medium shadow-none"
            aria-label={t("conversations.newConversation.agent")}
          >
            <AgentBadge type={agentKey} size="sm" tooltip={false} />
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {agents.map((a) => (
              <SelectItem key={a.agent_key} value={a.agent_key} disabled={!a.available}>
                {a.display_name}
                {a.available ? "" : ` (${t("conversations.newConversation.unavailable")})`}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {/* Offered with or without a connection: with none, the agent's built-in
            models (spec provider-switching "Serve one model list to every surface"). */}
        <ModelPicker
          agentKey={agentKey}
          value={modelValue}
          onCommit={(model) => onModelChange?.(model)}
        />
        {/* Renders nothing for an agent whose models report no levels. It is on
            the draft because the first turn runs the moment the conversation exists. */}
        <EffortPicker
          agentKey={agentKey}
          model={modelValue}
          value={effortValue}
          onCommit={(effort) => onEffortChange?.(effort)}
        />
      </div>

      <div className="flex flex-1 flex-col items-center justify-center gap-1.5 p-6 text-center">
        <p className="text-md font-semibold text-text">
          {t("conversations.draft.title", { agent: agentName })}
        </p>
        <p className="text-xs text-text-muted">{t("conversations.draft.details", { details })}</p>
      </div>
      <Composer
        onSend={onSend}
        disabled={creating}
        restore={restore}
        onRestored={onRestored}
        placeholder={t("conversations.composer.placeholder", { agent: agentName })}
      />
    </div>
  );
}
