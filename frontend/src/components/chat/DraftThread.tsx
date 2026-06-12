// src/components/chat/DraftThread.tsx
// The blank "new chat" surface shown before a conversation exists (the draft).
// The agent + its config (a model for the built-in agent, a working directory
// for a CLI agent) are chosen here in the top bar; sending the first message is
// what actually creates the conversation (see ChatPage.handleDraftSend).
import { useTranslation } from "react-i18next";
import { Bot } from "lucide-react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import type { AgentInfo } from "@/lib/api/chat";
import type { Model } from "@/lib/api/models";
import { Composer } from "./Composer";
import { ChatEmptyState } from "./ChatEmptyState";

interface Props {
  agents: AgentInfo[];
  models: Model[];
  agentKey: string;
  modelId: string | null;
  /** Working directory for a CLI agent (Claude Code / Codex). */
  cwd: string;
  onAgentChange: (agentKey: string) => void;
  onModelChange: (modelId: string | null) => void;
  onCwdChange: (cwd: string) => void;
  onSend: (text: string) => void;
  /** True while the create-then-send round-trip is in flight. */
  creating?: boolean;
}

export function DraftThread({
  agents,
  models,
  agentKey,
  modelId,
  cwd,
  onAgentChange,
  onModelChange,
  onCwdChange,
  onSend,
  creating = false,
}: Props) {
  const { t } = useTranslation();
  // CLI agents (Claude Code, Codex) are configured by a working directory; the
  // built-in agent by a model. "ready" decides whether the composer is enabled.
  const isCli = agentKey !== "builtin";
  const hasModel = models.length > 0;
  const ready = isCli ? cwd.trim().length > 0 : hasModel;
  const agentName =
    agents.find((a) => a.agent_key === agentKey)?.display_name ??
    t("chat.agent.cofferAssistant");

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Top bar: agent + its config (model or working directory), chosen before
          the first message rather than in a modal. */}
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

        {isCli ? (
          <div className="ml-auto flex items-center gap-2">
            <span className="text-xs text-muted-foreground">
              {t("chat.newConversation.workdir")}
            </span>
            <Input
              value={cwd}
              onChange={(e) => onCwdChange(e.target.value)}
              placeholder={t("chat.newConversation.workdirPlaceholder")}
              aria-label={t("chat.newConversation.workdir")}
              className="h-7 w-72 font-mono text-xs"
            />
          </div>
        ) : (
          hasModel && (
            <div className="ml-auto flex items-center gap-2">
              <span className="text-xs text-muted-foreground">{t("chat.modelBar.model")}</span>
              <Select value={modelId ?? ""} onValueChange={(v) => onModelChange(v || null)}>
                <SelectTrigger
                  className="h-7 w-44 text-xs"
                  aria-label={t("chat.modelBar.selectAria")}
                >
                  <SelectValue placeholder={t("chat.modelBar.noModel")} />
                </SelectTrigger>
                <SelectContent>
                  {models.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.display_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )
        )}
      </div>

      {!ready ? (
        isCli ? (
          <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
            <Bot className="mb-3 size-8 text-primary/70" strokeWidth={1.5} />
            <p className="text-sm text-muted-foreground">
              {t("chat.draft.workdirNeeded", { agent: agentName })}
            </p>
          </div>
        ) : (
          <ChatEmptyState />
        )
      ) : (
        <>
          <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
            <Bot className="mb-3 size-8 text-primary/70" strokeWidth={1.5} />
            <p className="text-sm text-muted-foreground">
              {t("chat.draft.guide", { agent: agentName })}
            </p>
          </div>
          <Composer onSend={onSend} disabled={creating} />
        </>
      )}
    </div>
  );
}
