// src/components/chat/ConversationsTable.tsx — the Conversations page's list
// (spec chat "Show every conversation on the Conversations page"): every
// conversation, newest activity first, under day headings — its title with a
// Running mark and the latest message's line, where it came from (SourceBadge),
// the agent it talks to, and the time of its last activity. A row opens the
// conversation; its title is the link, so the row reads right to a screen reader.
import type { KeyboardEvent, ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { StatusWord } from "@/components/status/StatusWord";
import { Skeleton } from "@/components/ui/skeleton";
import type { Conversation } from "@/lib/api/chat";
import { clock, dayHeading } from "@/lib/conversations/time";
import { cn } from "@/lib/utils";
import { SourceBadge } from "./SourceBadge";

interface Props {
  conversations: Conversation[];
  isLoading: boolean;
  /** Display name per agent key, from the agent registry. */
  agentNames: ReadonlyMap<string, string>;
  /** The link to one conversation, carrying the list's filters. */
  hrefFor: (id: string) => string;
}

const HEAD = "px-3 text-left text-2xs font-semibold text-text-muted";

export function ConversationsTable({ conversations, isLoading, agentNames, hrefFor }: Props) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const now = new Date();

  const onKey = (event: KeyboardEvent<HTMLTableRowElement>, id: string) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      navigate(hrefFor(id));
    }
  };

  const body: ReactNode[] = [];
  if (isLoading) {
    for (let i = 0; i < 4; i += 1) {
      body.push(
        <tr key={`skeleton-${i}`} className="h-[52px] border-b border-border-subtle">
          <td colSpan={4} className="px-3">
            <Skeleton className="h-4 w-2/3" />
          </td>
        </tr>,
      );
    }
  }
  let lastDay = "";
  for (const c of isLoading ? [] : conversations) {
    const day = dayHeading(t, c.updated_at, now, i18n.language);
    if (day !== lastDay) {
      lastDay = day;
      body.push(
        <tr key={`day:${day}:${c.id}`} aria-hidden>
          <td colSpan={4} className="px-3 pb-1 pt-4 text-2xs font-semibold text-text-muted">
            {day}
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
          "cursor-pointer border-b border-border-subtle transition-colors duration-fast",
          "hover:bg-surface-hover focus-within:bg-surface-hover",
        )}
      >
        <td className="max-w-0 px-3 py-2">
          <div className="flex min-w-0 items-center gap-2">
            <Link
              to={hrefFor(c.id)}
              onClick={(e) => e.stopPropagation()}
              className="truncate text-sm font-semibold text-text outline-none focus-visible:underline"
            >
              {c.title}
            </Link>
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

  return (
    <table
      className="w-full min-w-[40rem] table-fixed border-collapse"
      aria-label={t("conversations.list.ariaLabel")}
    >
      <thead>
        <tr className="h-[30px] border-b border-border-subtle">
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
