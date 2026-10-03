// src/components/chat/ConversationsList.tsx — the Conversations page's list
// (spec chat "Show every conversation on the Conversations page"): one
// bordered container of rows, newest activity first, under Today / Yesterday /
// Earlier bands that carry no counts. It has no header row; a row's checkbox
// shows on hover, and a shift-click ticks the range between two rows.
import { Fragment, useRef } from "react";
import { useTranslation } from "react-i18next";

import { Skeleton } from "@/components/ui/skeleton";
import type { Conversation } from "@/lib/api/chat";
import { groupByTime } from "@/lib/conversations/time";
import { ConversationRow } from "./ConversationRow";

interface Props {
  conversations: Conversation[];
  isLoading: boolean;
  /** A later page is loading: skeleton rows follow the last conversation. */
  loadingMore?: boolean;
  /** Display name per agent key, from the agent registry. */
  agentNames: ReadonlyMap<string, string>;
  /** The link to one conversation, carrying the list's filters. */
  hrefFor: (id: string) => string;
  archivedView: boolean;
  /** Row selection: the ticked ids, and a way to tick or untick several at once. */
  selection: {
    selected: ReadonlySet<string>;
    setMany: (ids: string[], on: boolean) => void;
  };
  onArchive: (c: Conversation) => void;
  onDelete: (c: Conversation) => void;
}

export function ConversationsList({
  conversations,
  isLoading,
  loadingMore = false,
  agentNames,
  hrefFor,
  archivedView,
  selection,
  onArchive,
  onDelete,
}: Props) {
  const { t } = useTranslation();
  const now = new Date();
  // Newest activity first, so each time group is one run of rows.
  const groups = groupByTime(conversations, (c) => c.updated_at, now);
  const ids = groups.flatMap((g) => g.items.map((c) => c.id));
  const { selected, setMany } = selection;
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

  const skeletons = (n: number, prefix: string) =>
    Array.from({ length: n }, (_, i) => (
      <li
        key={`${prefix}-${i}`}
        className="flex h-14 items-center border-t border-border-subtle px-3.5 first:border-t-0"
      >
        <Skeleton className="h-4 w-2/3" />
      </li>
    ));

  return (
    <ul
      aria-label={t("conversations.list.ariaLabel")}
      className="m-0 min-w-[42rem] list-none overflow-hidden rounded-xl border border-border bg-surface-raised p-0"
    >
      {isLoading ? skeletons(4, "skeleton") : null}
      {isLoading
        ? null
        : groups.map((g) => (
            <Fragment key={g.bucket}>
              <li
                aria-hidden
                className="flex h-7 items-center bg-surface-sunken pl-10 text-2xs font-semibold text-text-muted border-t border-border-subtle first:border-t-0"
              >
                {t(`conversations.group.${g.bucket}`)}
              </li>
              {g.items.map((c) => (
                <ConversationRow
                  key={c.id}
                  conversation={c}
                  href={hrefFor(c.id)}
                  agentName={agentNames.get(c.agent_key)}
                  selected={selected.has(c.id)}
                  selecting={selecting}
                  archivedView={archivedView}
                  now={now}
                  onToggle={(shift) => toggle(c.id, shift)}
                  onArchive={() => onArchive(c)}
                  onDelete={() => onDelete(c)}
                />
              ))}
            </Fragment>
          ))}
      {loadingMore ? skeletons(2, "more") : null}
    </ul>
  );
}
