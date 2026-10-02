// src/components/chat/DraftThread.tsx
// The draft New conversation opens (`/conversations/new`): a header with the
// chosen agent, its model and effort and the folder it will work in, an empty
// thread, and the composer whose first send creates the conversation (see
// useChatController.sendDraft) — no welcome or suggestions. The agent, folder,
// model and effort are all chosen here (New conversation asks nothing first). A hand-off opens it
// with a prompt already in the composer (`restore`), waiting for Send. When no managed
// agent is available, a state saying how to get one replaces the composer: the
// daemon's install prompt to copy, or the Agents page (NoManagedAgentHelp).
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
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
import { ConversationBackLink } from "./ConversationBackLink";
import { Composer } from "./Composer";
import { DraftWorkspacePicker } from "./DraftWorkspacePicker";
import { EffortPicker } from "./EffortPicker";
import { ModelPicker } from "./ModelPicker";
import { NoManagedAgentHelp } from "./NoManagedAgentHelp";

interface Props {
  agents: AgentProviderInfo[];
  /** The Conversations list the back link returns to, with its filters. */
  listPath: string;
  agentKey: string;
  /** The folder the turn will run in; null is Coffer's own workspace. */
  cwd?: string | null;
  /** True when no Coffer-managed agent is available (shows an empty state). */
  noManagedAgent?: boolean;
  onAgentChange: (agentKey: string) => void;
  onCwdChange?: (cwd: string | null) => void;
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
  listPath,
  agentKey,
  cwd = null,
  noManagedAgent = false,
  onAgentChange,
  onCwdChange,
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
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="flex h-[52px] shrink-0 items-center border-b border-border-subtle px-5">
          <ConversationBackLink listPath={listPath} />
        </div>
        <NoManagedAgentHelp layout="empty" />
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex h-[52px] shrink-0 items-center gap-3 border-b border-border-subtle px-5">
        <ConversationBackLink listPath={listPath} />
        <h1 className="text-md font-semibold text-text">{t("conversations.new.title")}</h1>
        <DraftWorkspacePicker cwd={cwd} onChange={(next) => onCwdChange?.(next)} />
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
        controls={
          <>
            <Select value={agentKey} onValueChange={onAgentChange}>
              <SelectTrigger
                className="h-control-sm w-auto gap-2 border-none bg-transparent px-1.5 text-xs font-medium shadow-none"
                aria-label={t("conversations.newConversation.agent")}
              >
                <AgentBadge type={agentKey} size="sm" tooltip={false} />
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {/* Only agents that can run are offered (spec chat "Create the
                conversation on the first send"): an unmanaged one cannot start. */}
                {agents
                  .filter((a) => a.available)
                  .map((a) => (
                    <SelectItem key={a.agent_key} value={a.agent_key}>
                      {a.display_name}
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
          </>
        }
        placeholder={t("conversations.composer.placeholder", { agent: agentName })}
      />
    </div>
  );
}
