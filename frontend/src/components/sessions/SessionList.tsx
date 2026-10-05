// src/components/sessions/SessionList.tsx — the bordered list of SessionRows
// under both the Conversations page and an agent's Sessions tab: a header row
// naming the columns the list shows, newest activity first, optionally under Today / Yesterday / Earlier bands that
// carry no counts, with skeleton rows while a page loads.
import { Fragment, useMemo } from "react";
import { useTranslation } from "react-i18next";

import { Skeleton } from "@/components/ui/skeleton";
import { groupByTime } from "@/lib/conversations/time";
import type { SessionRowData } from "@/lib/sessions/rows";
import { cn } from "@/lib/utils";
import { columnsOf, GRID, ROW_MIN_WIDTH, type SessionColumns } from "./columns";
import { SessionRow } from "./SessionRow";

type RowHandlers = Pick<
  React.ComponentProps<typeof SessionRow>,
  | "onPrimaryAction"
  | "terminalLabel"
  | "otherTerminals"
  | "onCopyCommand"
  | "canOpen"
  | "onRename"
  | "onDelete"
  | "onStop"
>;

interface Props extends RowHandlers {
  rows: SessionRowData[];
  ariaLabel: string;
  isLoading: boolean;
  /** A later page is loading: skeleton rows follow the last row. */
  loadingMore?: boolean;
  /** Show the channel column; by default only when some row came from a channel. */
  showChannel?: boolean;
  /** Group the rows under Today / Yesterday / Earlier. */
  grouped?: boolean;
  /** Display name per agent key, from the agent registry; set where rows show their agent. */
  agentNames?: ReadonlyMap<string, string>;
  /** The id of the row whose Stop is in flight. */
  stoppingId?: string | null;
}

const skeletons = (n: number, prefix: string) =>
  Array.from({ length: n }, (_, i) => (
    <li
      key={`${prefix}-${i}`}
      className="flex h-14 items-center border-t border-border-subtle px-3.5 first:border-t-0"
    >
      <Skeleton className="h-4 w-2/3" />
    </li>
  ));

/** The header row: one heading per column the list shows, over the row cells (the actions column has none). */
function HeaderRow({ columns }: { columns: SessionColumns }) {
  const { t } = useTranslation();
  const source = columns === "channel" || columns === "channel_agent";
  const agent = columns === "agent" || columns === "channel_agent";
  return (
    <li
      data-header
      className={cn(
        "grid h-8 items-center gap-x-3 pl-3.5 pr-2.5 text-2xs font-semibold text-text-muted",
        GRID[columns],
      )}
    >
      <span>{t("sessions.columns.title")}</span>
      {source ? <span>{t("sessions.columns.source")}</span> : null}
      {agent ? <span>{t("sessions.columns.agent")}</span> : null}
      <span>{t("sessions.columns.directory")}</span>
      <span className="text-right">{t("sessions.columns.lastActive")}</span>
      <span aria-hidden />
    </li>
  );
}

export function SessionList({
  rows,
  ariaLabel,
  isLoading,
  loadingMore = false,
  grouped = false,
  showChannel,
  agentNames,
  stoppingId = null,
  ...handlers
}: Props) {
  const { t } = useTranslation();
  const now = new Date();
  const anyChannel = useMemo(() => rows.some((r) => r.channel !== null), [rows]);
  const columns = columnsOf(showChannel ?? anyChannel, agentNames !== undefined);
  const item = (row: SessionRowData) => (
    <SessionRow
      key={row.id}
      row={row}
      columns={columns}
      agentName={row.agentKey ? agentNames?.get(row.agentKey) : undefined}
      now={now}
      stopping={stoppingId === row.id}
      {...handlers}
    />
  );
  const groups = useMemo(
    () => (grouped ? groupByTime(rows, (r) => r.activityAt ?? "", new Date()) : []),
    [grouped, rows],
  );

  return (
    <ul
      aria-label={ariaLabel}
      className={cn(
        "m-0 list-none overflow-hidden rounded-xl border border-border bg-surface-raised p-0",
        ROW_MIN_WIDTH[columns],
      )}
    >
      <HeaderRow columns={columns} />
      {isLoading ? skeletons(4, "skeleton") : null}
      {isLoading
        ? null
        : grouped
          ? groups.map((g) => (
              <Fragment key={g.bucket}>
                <li
                  data-band={g.bucket}
                  className="flex h-7 items-center border-t border-border-subtle bg-surface-sunken pl-3.5 text-2xs font-semibold text-text-muted first:border-t-0"
                >
                  <span aria-hidden>{t(`conversations.group.${g.bucket}`)}</span>
                </li>
                {g.items.map(item)}
              </Fragment>
            ))
          : rows.map(item)}
      {loadingMore ? skeletons(2, "more") : null}
    </ul>
  );
}
