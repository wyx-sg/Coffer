// src/components/chat/ConversationsList.tsx — the Conversations page's list
// (spec chat "Show every conversation on the Conversations page"): one
// bordered container of rows, newest activity first, under Today / Yesterday /
// Earlier bands that carry no counts. It has no header row: the first band
// holds Select all, in the column of the rows' checkboxes. A checkbox shows on
// hover, and a shift-click ticks the range between two rows.
import { Fragment, useRef } from "react";
import { useTranslation } from "react-i18next";

import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
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
  /** Select all: every conversation the view holds, loaded or not; ticked again, none. */
  selectAll: {
    checked: boolean;
    indeterminate: boolean;
    onToggle: () => void;
  };
  onArchive: (c: Conversation) => void;
  onDelete: (c: Conversation) => void;
}

// Hidden (its space kept) until the pointer or focus is on the list.
const REVEAL =
  "opacity-0 transition-opacity duration-fast group-hover/list:opacity-100 focus-within:opacity-100";

export function ConversationsList({
  conversations,
  isLoading,
  loadingMore = false,
  agentNames,
  hrefFor,
  archivedView,
  selection,
  selectAll,
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
      className="group/list m-0 min-w-[42rem] list-none overflow-hidden rounded-xl border border-border bg-surface-raised p-0"
    >
      {isLoading ? skeletons(4, "skeleton") : null}
      {isLoading
        ? null
        : groups.map((g, i) => (
            <Fragment key={g.bucket}>
              <li
                data-band={g.bucket}
                className="flex h-7 items-center gap-x-3 border-t border-border-subtle bg-surface-sunken pl-3.5 text-2xs font-semibold text-text-muted first:border-t-0"
              >
                {i === 0 ? (
                  <span
                    className={cn(
                      "inline-flex",
                      !(selecting || selectAll.checked || selectAll.indeterminate) && REVEAL,
                    )}
                  >
                    <Checkbox
                      checked={selectAll.checked}
                      indeterminate={selectAll.indeterminate}
                      aria-label={t("common.bulk.selectAll")}
                      onChange={selectAll.onToggle}
                    />
                  </span>
                ) : (
                  <span aria-hidden className="w-[15px] shrink-0" />
                )}
                <span aria-hidden>{t(`conversations.group.${g.bucket}`)}</span>
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
