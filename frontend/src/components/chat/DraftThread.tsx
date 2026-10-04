// src/components/chat/DraftThread.tsx
// The draft New conversation opens (`/conversations/new`): "New conversation" in
// the title bar, one line saying which agent will run in which folder, and the
// composer whose first send creates the conversation (see
// useChatController.sendDraft) — no welcome or suggestions. The folder picker
// sits in the composer's toolbar beside the paperclip; the agent, model and
// effort on its right. A hand-off (Ask an agent) opens it with a prompt already
// in the composer (`restore`), waiting for Send, and says so under the box. When
// no managed agent is available, a state with a way to the Agents page replaces
// the composer (NoManagedAgentHelp).
import { Trans, useTranslation } from "react-i18next";

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
import type { ComposerRestore } from "@/lib/hooks/useComposerRestore";
import { Composer } from "./Composer";
import { DraftTitleBar } from "./ConversationHeader";
import { DraftWorkspacePicker } from "./DraftWorkspacePicker";
import { EffortPicker } from "./EffortPicker";
import { ModelPicker } from "./ModelPicker";
import { NoManagedAgentHelp } from "./NoManagedAgentHelp";

interface Props {
  agents: AgentProviderInfo[];
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
  /** Opened from Ask an agent: say nothing is sent until Send. */
  fromHandoff?: boolean;
}

export function DraftThread({
  agents,
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
  fromHandoff = false,
}: Props) {
  const { t } = useTranslation();
  const agentName = agents.find((a) => a.agent_key === agentKey)?.display_name ?? agentKey;
  const dir = cwd ? abbreviateHomePath(cwd) : t("conversations.draft.workspace");

  if (noManagedAgent) {
    return (
      <div className="flex flex-1 flex-col overflow-hidden">
        <DraftTitleBar />
        <NoManagedAgentHelp />
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <DraftTitleBar />
      <div className="flex flex-1 items-center justify-center px-8 text-center">
        <p className="text-sm text-text-muted">
          <Trans
            i18nKey="conversations.draft.line"
            values={{ agent: agentName, dir }}
            components={{ mono: <span className="font-mono" /> }}
          />
        </p>
      </div>
      <Composer
        onSend={onSend}
        disabled={creating}
        restore={restore}
        onRestored={onRestored}
        note={fromHandoff ? t("conversations.draft.handoffNote") : undefined}
        workspace={<DraftWorkspacePicker cwd={cwd} onChange={(next) => onCwdChange?.(next)} />}
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
