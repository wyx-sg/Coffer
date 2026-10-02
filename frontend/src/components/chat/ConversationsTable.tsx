// src/components/chat/ConversationsTable.tsx — the Conversations page's list
// (spec chat "Show every conversation on the Conversations page"): every
// conversation, newest activity first, under time-group headings (Today, Yesterday, Previous 7 days…) — its title with a
// Running mark and the latest message's line, where it came from (SourceBadge),
// the agent it talks to, and the time of its last activity. A row opens the
// conversation; its title is the link, so the row reads right to a screen reader.
import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { StatusWord } from "@/components/status/StatusWord";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import type { Conversation } from "@/lib/api/chat";
import { clock, groupByTime, timeBucket } from "@/lib/conversations/time";
import { cn } from "@/lib/utils";
import { SourceBadge } from "./SourceBadge";

interface Props {
  conversations: Conversation[];
  isLoading: boolean;
  /** A later page is loading: skeleton rows follow the last conversation. */
  loadingMore?: boolean;
  /** Display name per agent key, from the agent registry. */
  agentNames: ReadonlyMap<string, string>;
  /** The link to one conversation, carrying the list's filters. */
  hrefFor: (id: string) => string;
  /** A line under the column heads that says how this view behaves. */
  notice?: string;
  /** Row selection: the ticked ids, and a way to tick or untick several at once. */
  selection: {
    selected: ReadonlySet<string>;
    setMany: (ids: string[], on: boolean) => void;
  };
}

const HEAD = "px-3 text-left text-2xs font-semibold text-text-muted";

// Hidden (its space kept) until the pointer or focus is on the row.
const REVEAL =
  "opacity-0 transition-opacity duration-fast group-hover/row:opacity-100 group-focus-within/row:opacity-100 focus-within:opacity-100";

export function ConversationsTable({
  conversations,
  isLoading,
  loadingMore = false,
  agentNames,
  hrefFor,
  notice,
  selection,
}: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const now = new Date();
  // Newest activity first, so each time group is one run of rows.
  const sorted = groupByTime(conversations, (c) => c.updated_at, now).flatMap((g) => g.items);

  const ids = sorted.map((c) => c.id);
  const { selected, setMany } = selection;
  const allOn = ids.length > 0 && ids.every((id) => selected.has(id));
  const someOn = !allOn && ids.some((id) => selected.has(id));
  // Every checkbox stays shown once any row is ticked; until then each appears on hover.
  const selecting = selected.size > 0;
  // The row last ticked: a shift-click ticks (or unticks) everything between it and the click.
  const anchor = useRef<string | null>(null);
  const toggle = (id: string, range: boolean) => {
    const on = !selected.has(id);
    const from = anchor.current ? ids.indexOf(anchor.current) : -1;
    const to = ids.indexOf(id);
    setMany(range && from >= 0 ? ids.slice(Math.min(from, to), Math.max(from, to) + 1) : [id], on);
    anchor.current = id;
  };

  const onKey = (event: KeyboardEvent<HTMLTableRowElement>, id: string) => {
    if (event.target !== event.currentTarget) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      navigate(hrefFor(id));
    }
  };

  const body: ReactNode[] = [];
  if (notice) {
    body.push(
      <tr key="notice" className="border-b border-border-subtle bg-surface-sunken">
        <td colSpan={5} className="px-3 py-2 text-xs text-text-muted">
          {notice}
        </td>
      </tr>,
    );
  }
  if (isLoading) {
    for (let i = 0; i < 4; i += 1) {
      body.push(
        <tr key={`skeleton-${i}`} className="h-[52px] border-b border-border-subtle">
          <td colSpan={5} className="px-3">
            <Skeleton className="h-4 w-2/3" />
          </td>
        </tr>,
      );
    }
  }
  let lastGroup = "";
  for (const c of isLoading ? [] : sorted) {
    const group = timeBucket(c.updated_at, now);
    if (group !== lastGroup) {
      lastGroup = group;
      body.push(
        <tr key={`group:${group}`} aria-hidden>
          <td colSpan={5} className="px-3 pb-1 pt-4 text-2xs font-semibold text-text-muted">
            {t(`conversations.group.${group}`)}
          </td>
        </tr>,
      );
    }
    body.push(
      <tr
        key={c.id}
        tabIndex={-1}
        data-conversation={c.id}
        onClick={() => navigate(hrefFor(c.id))}
        onKeyDown={(e) => onKey(e, c.id)}
        className={cn(
          "group/row cursor-pointer border-b border-border-subtle transition-colors duration-fast",
          "hover:bg-surface-hover focus-within:bg-surface-hover",
          selected.has(c.id) && "bg-accent-soft",
        )}
      >
        <td className="px-3" onClick={(e) => e.stopPropagation()}>
          <span className={cn("inline-flex", !selecting && REVEAL)}>
            <Checkbox
              checked={selected.has(c.id)}
              aria-label={t("conversations.bulk.selectRow", { title: c.title })}
              onChange={() => undefined}
              onClick={(e) => toggle(c.id, e.shiftKey)}
            />
          </span>
        </td>
        <td className="max-w-0 px-3 py-2">
          <div className="flex min-w-0 items-center gap-2">
            <Link
              to={hrefFor(c.id)}
              onClick={(e) => e.stopPropagation()}
              className="truncate text-sm font-semibold text-text outline-none focus-visible:underline"
            >
              {c.title}
            </Link>
            {c.archived_at ? (
              <span className="shrink-0 text-2xs text-text-subtle">
                {t("conversations.header.archived")}
              </span>
            ) : null}
            {c.running ? (
              <StatusWord tone="ok" className="shrink-0">
                {t("conversations.list.running")}
              </StatusWord>
            ) : null}
          </div>
          {c.preview ? <p className="truncate text-xs text-text-muted">{c.preview}</p> : null}
        </td>
        <td className="max-w-0 px-3">
          <SourceBadge conversation={c} className="max-w-full" />
        </td>
        <td className="px-3">
          <AgentBadge
            type={c.agent_key}
            name={agentNames.get(c.agent_key)}
            size="sm"
            showName
            tooltip={false}
          />
        </td>
        <td className="px-3 text-right">
          <time dateTime={c.updated_at} className="font-mono text-xs text-text-muted">
            {clock(c.updated_at)}
          </time>
        </td>
      </tr>,
    );
  }

  if (loadingMore) {
    for (let i = 0; i < 2; i += 1) {
      body.push(
        <tr key={`more-${i}`} className="h-[52px] border-b border-border-subtle">
          <td colSpan={5} className="px-3">
            <Skeleton className="h-4 w-1/2" />
          </td>
        </tr>,
      );
    }
  }

  return (
    <table
      className="w-full min-w-[42rem] table-fixed border-collapse"
      aria-label={t("conversations.list.ariaLabel")}
    >
      <thead>
        <tr className="group/row h-[30px] border-b border-border-subtle">
          <th scope="col" className="w-10 px-3">
            <span className={cn("inline-flex", !selecting && REVEAL)}>
              <Checkbox
                checked={allOn}
                indeterminate={someOn}
                aria-label={t("conversations.bulk.selectAll")}
                onChange={() => setMany(ids, !allOn)}
              />
            </span>
          </th>
          <th scope="col" className={HEAD}>
            {t("conversations.list.cols.conversation")}
          </th>
          <th scope="col" className={cn(HEAD, "w-60")}>
            {t("conversations.list.cols.source")}
          </th>
          <th scope="col" className={cn(HEAD, "w-36")}>
            {t("conversations.list.cols.agent")}
          </th>
          <th scope="col" className={cn(HEAD, "w-28 text-right")}>
            {t("conversations.list.cols.lastActivity")}
          </th>
        </tr>
      </thead>
      {/* Which conversations exist and when changes from run to run. */}
      <tbody data-visual-volatile>{body}</tbody>
    </table>
  );
}
