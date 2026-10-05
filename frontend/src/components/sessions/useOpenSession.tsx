// src/components/sessions/useOpenSession.tsx — what pressing a session row does,
// shared by the Conversations page and an agent's Sessions tab (spec chat "Open
// a conversation in the terminal" and "Ask before opening a session that is
// running"). The row's main action asks the daemon to resume its native session
// in the preferred terminal; its ▾ menu opens it in another terminal on this
// machine instead (once — the preference stays), and Copy command copies the
// same command line. A row
// whose turn is running or waits on a question first opens a dialog: answer in
// the chat, or stop the turn (the row's own Stop) and then open the terminal.
// The caller renders `dialog` once beside its list.
import { useCallback, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import type { AgentType } from "@/lib/api/agents";
import { platformName } from "@/lib/channels/platformName";
import { useInterruptConversation } from "@/lib/hooks/useConversations";
import {
  useOpenInTerminal,
  useTerminalChoices,
  type TerminalChoice,
} from "@/lib/hooks/useTerminals";
import type { SessionRowData } from "@/lib/sessions/rows";
import { resumeCommand } from "@/lib/terminal/command";

/** The agent type behind a registry key; null for one that has no terminal program. */
function agentTypeOf(key: string | null | undefined): AgentType | null {
  return key === "claude_code" || key === "codex" ? key : null;
}

/** The pieces of a list that opens its rows in a terminal. */
export interface SessionOpener {
  /** The row's main action — or, given `terminal`, the ▾ pick of another
   *  terminal; leaves a row without a session alone. */
  open: (row: SessionRowData, terminal?: string) => void;
  /** The preferred terminal's name ("Open in <terminal>"). */
  terminalLabel: string;
  /** The other terminals a row's ▾ menu offers. */
  otherTerminals: TerminalChoice[];
  /** Copy the row's resume command; leaves a row without a session alone. */
  copyCommand: (row: SessionRowData) => void;
  /** Whether the row has a session to open (the split button is disabled otherwise). */
  canOpen: (row: SessionRowData) => boolean;
  /** The busy dialog; render it once. */
  dialog: ReactNode;
}

/**
 * @param agentType the agent every row belongs to, where the list is one agent's;
 *   otherwise each row's own agent key says.
 */
export function useOpenSession(agentType?: AgentType): SessionOpener {
  const { t } = useTranslation();
  const { toast } = useToast();
  const openTerminal = useOpenInTerminal();
  const choices = useTerminalChoices();
  const stop = useInterruptConversation({ silent: true });
  // The busy row, and the terminal it was asked to open in (undefined: the preferred one).
  const [pending, setPending] = useState<{ row: SessionRowData; terminal?: string } | null>(null);
  const busy = pending?.row ?? null;

  const typeOf = useCallback(
    (row: SessionRowData) => agentType ?? agentTypeOf(row.agentKey),
    [agentType],
  );
  const canOpen = useCallback(
    (row: SessionRowData) => row.sessionId !== null && typeOf(row) !== null,
    [typeOf],
  );

  const copyCommand = useCallback(
    (row: SessionRowData) => {
      const agent = typeOf(row);
      if (!row.sessionId || !agent) return;
      const command = resumeCommand(agent, row.cwd, row.sessionId);
      void navigator.clipboard
        ?.writeText(command)
        .then(() => toast.success(t("terminal.commandCopied")));
    },
    [t, toast, typeOf],
  );

  const start = useCallback(
    async (row: SessionRowData, terminal?: string) => {
      const agent = typeOf(row);
      if (!row.sessionId || !agent) return;
      await openTerminal(
        { agent, cwd: row.cwd, resume: row.sessionId },
        { label: t("terminal.copyCommand"), onClick: () => copyCommand(row) },
        terminal,
      );
    },
    [copyCommand, openTerminal, t, typeOf],
  );

  const open = useCallback(
    (row: SessionRowData, terminal?: string) => {
      if (!canOpen(row)) return;
      if (row.running || row.needsYou) setPending({ row, terminal });
      else void start(row, terminal);
    },
    [canOpen, start],
  );

  const platform = busy?.channel?.platform
    ? platformName(busy.channel.platform)
    : t("sessions.busy.chat");
  const dialog = (
    <ConfirmDialog
      open={busy !== null}
      onOpenChange={(next) => !next && setPending(null)}
      title={t("sessions.busy.title")}
      description={t(busy?.needsYou ? "sessions.busy.waiting" : "sessions.busy.running", {
        platform,
      })}
      cancelLabel={t("sessions.busy.answer", { platform })}
      confirmLabel={t("sessions.busy.stop")}
      pendingLabel={t("sessions.busy.stopping")}
      errorTitle={t("sessions.busy.failed")}
      variant="default"
      pending={stop.isPending}
      onConfirm={async () => {
        if (!pending) return;
        const { row, terminal } = pending;
        if (row.conversationId) await stop.mutateAsync(row.conversationId);
        void start(row, terminal);
      }}
    />
  );

  return {
    open,
    copyCommand,
    canOpen,
    terminalLabel: choices.label,
    otherTerminals: choices.others,
    dialog,
  };
}
