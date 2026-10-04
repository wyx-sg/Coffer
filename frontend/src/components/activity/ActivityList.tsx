// src/components/activity/ActivityList.tsx — the visible tab's records as a table in a bordered box, grouped by day, each row opening its detail.
//
// One table component, four column sets (activityColumns). The day a group
// of rows falls on is a sunken heading row inside the box ("Today · Sep 29",
// design 6.2.01); the box's last row is the page's footer (load older, or the
// retention note). Selecting a row (click, Enter or Space) opens it in the
// drawer; on the Daemon log a row expands in place instead, under its own line
// (design 6.2.08). Only MCP calls' Took sorts, over the rows loaded; while a
// sort is on the day headings go, since the order no longer follows the days.
import type { KeyboardEvent, ReactNode } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import { useTranslation } from "react-i18next";

import { recordSeverity, type ActivityRecord, type ActivityTab } from "@/lib/activity/records";
import { dayLabel } from "@/lib/activity/recordText";
import { nextSort, type TableSort } from "@/lib/tableSort";
import { cn } from "@/lib/utils";
import { columnsFor, type Column } from "./activityColumns";
import type { AgentLook } from "./activityCells";

interface Props {
  tab: ActivityTab;
  rows: ActivityRecord[];
  agents: ReadonlyMap<string, AgentLook>;
  selectedKey: string | null;
  onSelect: (key: string) => void;
  /** The Daemon log row open in place, and what it shows. */
  renderExpanded?: (r: ActivityRecord) => ReactNode;
  sort: TableSort | null;
  onSort: (sort: TableSort | null) => void;
  /** The box's last row. */
  footer?: ReactNode;
}

/** The rows in `sort`'s order; the default order (newest first) when there is none. */
function sorted(rows: ActivityRecord[], columns: Column[], sort: TableSort | null) {
  const column = sort ? columns.find((c) => c.key === sort.key && c.sortable) : undefined;
  if (!sort || !column) return { rows, active: null };
  const sign = sort.dir === "desc" ? -1 : 1;
  const value = (r: ActivityRecord) => (r.source === "call" ? r.call.duration_ms : 0);
  return {
    rows: [...rows].sort((a, b) => (value(a) - value(b)) * sign),
    active: sort,
  };
}

function Head({
  column,
  active,
  onSort,
}: {
  column: Column;
  active: TableSort | null;
  onSort: () => void;
}) {
  if (!column.sortable) return <>{column.header}</>;
  const on = active?.key === column.key ? active : null;
  const Arrow = on?.dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <button
      type="button"
      onClick={onSort}
      className={cn(
        "-mx-1 inline-flex items-center gap-1 rounded-item px-1 py-0.5 hover:bg-surface-hover hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
        on && "text-text",
        column.align === "right" && "flex-row-reverse",
      )}
    >
      {column.header}
      {on ? <Arrow aria-hidden className="size-[11px]" /> : null}
    </button>
  );
}

export function ActivityList({
  tab,
  rows: loaded,
  agents,
  selectedKey,
  onSelect,
  renderExpanded,
  sort,
  onSort,
  footer,
}: Props) {
  const { t, i18n } = useTranslation();
  const columns = columnsFor(tab, t, agents);
  const { rows, active } = sorted(loaded, columns, sort);
  const now = new Date();
  const today = dayLabel(t, now.toISOString(), now, i18n.language);
  // The Daemon log marks only a day other than today; the other tabs always
  // name the day their rows fall on.
  const named = tab !== "daemon";

  const onKey = (event: KeyboardEvent<HTMLTableRowElement>, key: string) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(key);
    }
  };

  const cellClass = (c: Column, i: number) =>
    cn(
      "max-w-0 align-middle",
      i === 0 ? "pl-3 pr-[5px]" : i === columns.length - 1 ? "pl-[5px] pr-3" : "px-[5px]",
      c.align === "right" && "text-right",
    );

  const body: ReactNode[] = [];
  let lastDay: string | null = named ? null : today;
  for (const r of rows) {
    const day = dayLabel(t, r.at, now, i18n.language);
    if (!active && day !== lastDay) {
      body.push(
        <tr key={`day:${day}:${r.key}`} aria-hidden>
          <td
            colSpan={columns.length}
            className="h-[30px] border-b border-border-subtle bg-surface-sunken px-3 text-xs font-semibold text-text-muted"
          >
            {day}
          </td>
        </tr>,
      );
      lastDay = day;
    }
    const selected = r.key === selectedKey;
    const expanded = selected && renderExpanded ? renderExpanded(r) : null;
    const failing = tab === "daemon" && recordSeverity(r) === "error";
    body.push(
      <tr
        key={r.key}
        tabIndex={0}
        aria-selected={selected}
        aria-expanded={renderExpanded ? selected : undefined}
        data-record={r.key}
        onClick={() => onSelect(r.key)}
        onKeyDown={(e) => onKey(e, r.key)}
        className={cn(
          "cursor-pointer border-b border-border-subtle outline-none transition-colors duration-fast last:border-b-0",
          tab === "daemon" ? "h-8" : "h-[38px]",
          "hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring",
          selected && "bg-surface-selected hover:bg-surface-selected",
          selected && failing && "shadow-[inset_2px_0_0_rgb(var(--danger))]",
        )}
      >
        {columns.map((c, i) => (
          <td key={c.key} className={cellClass(c, i)}>
            {c.cell(r)}
          </td>
        ))}
      </tr>,
    );
    if (expanded) {
      body.push(
        <tr
          key={`${r.key}:open`}
          className={cn(
            "border-b border-border-subtle bg-surface-selected",
            failing && "shadow-[inset_2px_0_0_rgb(var(--danger))]",
          )}
        >
          <td colSpan={columns.length} className="max-w-0 pb-3 pl-3 pr-3 pt-2.5">
            {expanded}
          </td>
        </tr>,
      );
    }
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface-raised">
      <table
        className="w-full min-w-[36rem] table-fixed border-collapse"
        aria-label={t(`activity.tabs.${tab}`)}
      >
        <colgroup>
          {columns.map((c, i) => (
            <col
              key={c.key}
              style={
                c.width
                  ? { width: c.width + 10 + (i === 0 || i === columns.length - 1 ? 2 : 0) }
                  : undefined
              }
            />
          ))}
        </colgroup>
        <thead>
          <tr className="h-[34px] border-b border-border-subtle">
            {columns.map((c, i) => (
              <th
                key={c.key}
                scope="col"
                aria-sort={
                  c.sortable
                    ? active?.key === c.key
                      ? active.dir === "asc"
                        ? "ascending"
                        : "descending"
                      : "none"
                    : undefined
                }
                className={cn("text-left text-2xs font-semibold text-text-subtle", cellClass(c, i))}
              >
                <Head column={c} active={active} onSort={() => onSort(nextSort(sort, c.key))} />
              </th>
            ))}
          </tr>
        </thead>
        {/* Which records exist, and how many, changes from run to run; screenshot
          tests mask it and show a fixed number of rows. */}
        <tbody data-visual-volatile="rows">{body}</tbody>
      </table>
      {footer}
    </div>
  );
}
