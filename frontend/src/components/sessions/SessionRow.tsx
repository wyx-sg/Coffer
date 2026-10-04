// src/components/sessions/SessionRow.tsx — one row of a session list, shared by
// the Conversations page and an agent's Sessions tab (spec chat "Show channel
// conversations on the Conversations page", agent-registry "Open an agent's
// sessions from its Sessions tab"): the title with a status word, the channel
// it came from, the agent (where the list spans agents), the working
// directory, when it was last active, an inline Stop while a turn runs and a
// ⋯ menu with Rename and Delete…. Rename edits the title in place — Enter
// saves, Esc cancels. The row's primary action is `onPrimaryAction` (Open in
// terminal, spec chat "Open a conversation in the terminal"): pressing the row
// or the main part of its split button runs it, and the ▾ menu holds Copy
// command. A row with no native session yet shows the split button disabled,
// with the reason in a tooltip. A list that has no primary action leaves the
// row inert.
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { Copy, Pencil, Square, SquareTerminal, Trash2 } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import { SplitButton } from "@/components/ui/split-button";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import { TruncatedText } from "@/components/ui/truncated-text";
import { abbreviateHomePath } from "@/lib/agents/display";
import { rowTime } from "@/lib/conversations/time";
import type { SessionRowData } from "@/lib/sessions/rows";
import { cn } from "@/lib/utils";
import { GRID, type SessionColumns } from "./columns";
import { SourceBadge } from "./SourceBadge";

// Hidden (its space kept) until the pointer or focus is on the row.
const REVEAL =
  "opacity-0 transition-opacity duration-fast group-hover/row:opacity-100 group-focus-within/row:opacity-100 focus-within:opacity-100";

interface Props {
  row: SessionRowData;
  columns: SessionColumns;
  /** The agent's display name, from the registry. */
  agentName?: string;
  now: Date;
  /** What pressing the row does; leave out and the row is inert. */
  onPrimaryAction?: (row: SessionRowData) => void;
  /** Copies the row's resume command (the split button's ▾ menu). */
  onCopyCommand?: (row: SessionRowData) => void;
  /** Whether the row has a session to open; a row that has none is disabled. Default: it does. */
  canOpen?: (row: SessionRowData) => boolean;
  /** Saves a new title; the row keeps its editor until this settles. */
  onRename: (row: SessionRowData, title: string) => Promise<unknown>;
  onDelete: (row: SessionRowData) => void;
  /** Stops the turn running on the row (only a running row shows Stop). */
  onStop?: (row: SessionRowData) => void;
  stopping?: boolean;
}

export function SessionRow({
  row,
  columns,
  agentName,
  now,
  onPrimaryAction,
  onCopyCommand,
  canOpen = () => true,
  onRename,
  onDelete,
  onStop,
  stopping = false,
}: Props) {
  const { t, i18n } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(row.title);
  const [saving, setSaving] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  // The menu returns focus to its trigger as it closes; take it back once it has.
  useEffect(() => {
    if (!editing) return;
    input.current?.focus();
    input.current?.select();
    const id = window.setTimeout(() => {
      if (document.activeElement !== input.current) input.current?.focus();
    }, 250);
    return () => window.clearTimeout(id);
  }, [editing]);

  const startRename = () => {
    setDraft(row.title);
    setEditing(true);
  };
  const save = async () => {
    const title = draft.trim();
    if (!title || title === row.title) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await onRename(row, title);
    } catch {
      // The mutation toasts the refusal; the row keeps its title.
    } finally {
      setSaving(false);
      setEditing(false);
    }
  };
  const onEditKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void save();
    } else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      setEditing(false);
    }
  };
  const openable = onPrimaryAction !== undefined && canOpen(row);
  const onRowKey = (event: KeyboardEvent<HTMLLIElement>) => {
    if (event.target !== event.currentTarget || !openable) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onPrimaryAction?.(row);
    }
  };

  const actions: MenuAction[] = [
    { key: "rename", label: t("sessions.row.rename"), icon: Pencil, onSelect: startRename },
    {
      key: "delete",
      label: t("sessions.row.delete"),
      icon: Trash2,
      destructive: true,
      separated: true,
      onSelect: () => onDelete(row),
    },
  ];

  return (
    <li
      tabIndex={openable ? 0 : -1}
      data-session={row.id}
      onClick={openable && !editing ? () => onPrimaryAction?.(row) : undefined}
      onKeyDown={onRowKey}
      className={cn(
        "group/row grid min-h-14 items-center gap-x-3 border-t border-border-subtle py-2 pl-3.5 pr-2.5 transition-colors duration-fast",
        GRID[columns],
        "hover:bg-surface-hover focus-within:bg-surface-hover",
        openable && "cursor-pointer",
      )}
    >
      <div className="flex min-w-0 items-center gap-2.5">
        {editing ? (
          <input
            ref={input}
            value={draft}
            disabled={saving}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onEditKey}
            onClick={(e) => e.stopPropagation()}
            aria-label={t("sessions.row.titleAria")}
            className="h-control-sm min-w-0 flex-1 rounded-md border border-accent bg-surface-raised px-2 text-sm font-label text-text outline-none ring-[3px] ring-accent-soft"
          />
        ) : (
          <>
            <TruncatedText text={row.title} className="text-sm font-label text-text" />
            {row.needsYou ? (
              <StatusWord tone="warn" className="shrink-0">
                {t("sessions.row.needsYou")}
              </StatusWord>
            ) : row.running ? (
              <StatusWord tone="ok" className="shrink-0">
                {t("sessions.row.running")}
              </StatusWord>
            ) : null}
          </>
        )}
      </div>
      {columns === "channel" || columns === "channel_agent" ? (
        row.channel ? (
          <SourceBadge channel={row.channel} className="max-w-full" />
        ) : (
          <span />
        )
      ) : null}
      {columns === "agent" || columns === "channel_agent" ? (
        row.agentKey ? (
          <AgentBadge type={row.agentKey} name={agentName} size="sm" showName tooltip={false} />
        ) : (
          <span />
        )
      ) : null}
      {row.cwd ? (
        <TruncatedText text={row.cwd} mono className="text-xs text-text-muted">
          {abbreviateHomePath(row.cwd)}
        </TruncatedText>
      ) : (
        <span className="text-xs text-text-subtle">—</span>
      )}
      <time dateTime={row.activityAt ?? undefined} className="text-right text-xs text-text-muted">
        {row.activityAt ? rowTime(row.activityAt, now, i18n.language) : "—"}
      </time>
      <span className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
        {row.running && row.conversationId && onStop ? (
          <Button
            variant="outline"
            size="sm"
            loading={stopping}
            aria-label={t("sessions.row.stopAria", { title: row.title })}
            onClick={() => onStop(row)}
          >
            <Square aria-hidden className="!size-3 fill-current" />
            {t("sessions.row.stop")}
          </Button>
        ) : null}
        {onPrimaryAction ? (
          <span className={cn("inline-flex", REVEAL)}>
            <SplitButton
              size="sm"
              icon={<SquareTerminal aria-hidden />}
              label={t("sessions.row.open")}
              disabled={!openable}
              tooltip={openable ? undefined : t("sessions.row.noSession")}
              onClick={() => onPrimaryAction(row)}
              menuLabel={t("sessions.row.openOptions", { title: row.title })}
              actions={
                openable && onCopyCommand
                  ? [
                      {
                        key: "copy-command",
                        label: t("sessions.row.copyCommand"),
                        icon: Copy,
                        onSelect: () => onCopyCommand(row),
                      },
                    ]
                  : []
              }
            />
          </span>
        ) : null}
        <span className={cn("inline-flex", REVEAL)}>
          <ActionMenu
            label={t("sessions.row.moreActions", { title: row.title })}
            actions={actions}
          />
        </span>
      </span>
    </li>
  );
}
