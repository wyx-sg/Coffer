// src/components/chat/DraftThread.tsx
// The blank "new chat" surface shown before a conversation exists (the draft).
// Chat talks only to Coffer-managed agents (Claude Code / Codex), each
// configured by a working directory chosen here in the top bar; sending the
// first message is what actually creates the conversation (see
// useChatController.sendDraft). When no managed agent is available, an
// install/configure empty state is shown instead.
import { useTranslation } from "react-i18next";
import { Bot, History, MessageSquareOff } from "lucide-react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { FolderPicker } from "@/components/agents/FolderPicker";
import type { AgentInfo } from "@/lib/api/chat";
import { Composer } from "./Composer";

interface Props {
  agents: AgentInfo[];
  agentKey: string;
  /** Working directory for the managed agent (Claude Code / Codex). */
  cwd: string;
  /** Recently-used working directories, most-recent first. */
  recentCwds?: string[];
  /** True when no Coffer-managed agent is available (shows an empty state). */
  noManagedAgent?: boolean;
  onAgentChange: (agentKey: string) => void;
  onCwdChange: (cwd: string) => void;
  onSend: (text: string) => void;
  /** True while the create-then-send round-trip is in flight. */
  creating?: boolean;
}

export function DraftThread({
  agents,
  agentKey,
  cwd,
  recentCwds = [],
  noManagedAgent = false,
  onAgentChange,
  onCwdChange,
  onSend,
  creating = false,
}: Props) {
  const { t } = useTranslation();
  // Managed agents (Claude Code, Codex) are configured by a working directory;
  // "ready" decides whether the composer is enabled.
  const ready = cwd.trim().length > 0;
  const agentName = agents.find((a) => a.agent_key === agentKey)?.display_name ?? agentKey;

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

        <div className="ml-auto flex items-center gap-1.5">
          <span className="text-xs text-muted-foreground">{t("chat.newConversation.workdir")}</span>
          <Input
            value={cwd}
            onChange={(e) => onCwdChange(e.target.value)}
            placeholder={t("chat.newConversation.workdirPlaceholder")}
            aria-label={t("chat.newConversation.workdir")}
            className="h-7 w-64 font-mono text-xs"
          />
          {recentCwds.length > 0 && (
            <Popover>
              <PopoverTrigger asChild>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="size-7 shrink-0 p-0"
                  aria-label={t("chat.newConversation.recent")}
                >
                  <History className="size-4" />
                </Button>
              </PopoverTrigger>
              <PopoverContent align="end" className="w-72 p-1">
                <p className="px-2 py-1.5 text-xs font-medium text-muted-foreground">
                  {t("chat.newConversation.recent")}
                </p>
                <ul>
                  {recentCwds.map((p) => (
                    <li key={p}>
                      <button
                        type="button"
                        onClick={() => onCwdChange(p)}
                        className="block w-full truncate rounded px-2 py-1.5 text-left font-mono text-xs hover:bg-accent"
                        title={p}
                      >
                        {p}
                      </button>
                    </li>
                  ))}
                </ul>
              </PopoverContent>
            </Popover>
          )}
          <FolderPicker value={cwd || null} onChange={onCwdChange} />
        </div>
      </div>

      {!ready ? (
        <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
          <Bot className="mb-3 size-8 text-primary/70" strokeWidth={1.5} />
          <p className="text-sm text-muted-foreground">
            {t("chat.draft.workdirNeeded", { agent: agentName })}
          </p>
        </div>
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
