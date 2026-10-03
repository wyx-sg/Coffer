// src/components/chat/ConversationRow.tsx — one row of the Conversations list
// (spec chat "Show every conversation on the Conversations page"): a leading
// checkbox that shows on hover, the title with a status word and the latest
// line, where it came from, the agent, when it was last active, and a trailing
// ⋯ menu. The row opens the conversation; its title is the link, so the row
// reads right to a screen reader.
import { type KeyboardEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Archive, ArchiveRestore, Pencil, Trash2 } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { StatusWord } from "@/components/status/StatusWord";
import { Checkbox } from "@/components/ui/checkbox";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import type { Conversation } from "@/lib/api/chat";
import { rowTime } from "@/lib/conversations/time";
import { cn } from "@/lib/utils";
import { SourceBadge } from "./SourceBadge";

/** The columns: checkbox, text, source, agent, time, menu. */
const ROW_GRID = "grid grid-cols-[14px_minmax(0,1fr)_210px_120px_52px_26px] items-center gap-x-3";

// Hidden (its space kept) until the pointer or focus is on the row.
const REVEAL =
  "opacity-0 transition-opacity duration-fast group-hover/row:opacity-100 group-focus-within/row:opacity-100 focus-within:opacity-100";

interface Props {
  conversation: Conversation;
  href: string;
  agentName: string | undefined;
  selected: boolean;
  /** Something is ticked: every checkbox stays shown. */
  selecting: boolean;
  archivedView: boolean;
  now: Date;
  onToggle: (shift: boolean) => void;
  onArchive: () => void;
  onDelete: () => void;
}

export function ConversationRow({
  conversation: c,
  href,
  agentName,
  selected,
  selecting,
  archivedView,
  now,
  onToggle,
  onArchive,
  onDelete,
}: Props) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  // `needs_you` is supplied by the add-coffer-ask change; until the API sends it
  // the field is simply absent.
  const needsYou = (c as { needs_you?: boolean }).needs_you === true;

  const onKey = (event: KeyboardEvent<HTMLLIElement>) => {
    if (event.target !== event.currentTarget) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      navigate(href);
    }
  };

  const actions: MenuAction[] = [
    {
      key: "rename",
      label: t("conversations.history.rename"),
      icon: Pencil,
      // The open conversation reads this and starts editing its title.
      onSelect: () => navigate(href, { state: { rename: true } }),
    },
    {
      key: "archive",
      label: archivedView
        ? t("conversations.history.unarchive")
        : t("conversations.history.archive"),
      icon: archivedView ? ArchiveRestore : Archive,
      onSelect: onArchive,
    },
    {
      key: "delete",
      label: t("conversations.history.delete"),
      icon: Trash2,
      destructive: true,
      separated: true,
      onSelect: onDelete,
    },
  ];
  // Archived conversations are read-only: renaming one is not offered.
  const menu = archivedView ? actions.filter((a) => a.key !== "rename") : actions;

  return (
    <li
      tabIndex={-1}
      data-conversation={c.id}
      onClick={() => navigate(href)}
      onKeyDown={onKey}
      className={cn(
        ROW_GRID,
        "group/row min-h-14 cursor-pointer border-t border-border-subtle py-2 pl-3.5 pr-2.5 transition-colors duration-fast",
        "hover:bg-surface-hover focus-within:bg-surface-hover",
        selected && "bg-accent-soft",
      )}
    >
      <span
        className={cn("inline-flex", !selecting && !selected && REVEAL)}
        onClick={(e) => e.stopPropagation()}
      >
        <Checkbox
          checked={selected}
          aria-label={t("conversations.bulk.selectRow", { title: c.title })}
          onChange={() => undefined}
          onClick={(e) => onToggle(e.shiftKey)}
        />
      </span>
      <div className="flex min-w-0 flex-col gap-[3px]">
        <div className="flex min-w-0 items-center gap-2.5">
          <Link
            to={href}
            onClick={(e) => e.stopPropagation()}
            className="truncate text-sm font-label text-text outline-none focus-visible:underline"
          >
            {c.title}
          </Link>
          {needsYou ? (
            <StatusWord tone="warn" className="shrink-0">
              {t("conversations.list.needsYou")}
            </StatusWord>
          ) : c.running ? (
            <StatusWord tone="ok" className="shrink-0">
              {t("conversations.list.running")}
            </StatusWord>
          ) : null}
        </div>
        {c.preview ? <p className="truncate text-xs text-text-muted">{c.preview}</p> : null}
      </div>
      <SourceBadge conversation={c} className="max-w-full" />
      <AgentBadge type={c.agent_key} name={agentName} size="sm" showName tooltip={false} />
      <time dateTime={c.updated_at} className="text-right text-xs text-text-muted">
        {rowTime(c.updated_at, now, i18n.language)}
      </time>
      <span className={cn("inline-flex", REVEAL)} onClick={(e) => e.stopPropagation()}>
        <ActionMenu label={t("common.moreActions")} actions={menu} />
      </span>
    </li>
  );
}
