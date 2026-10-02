// src/components/activity/ActivityList.tsx — the visible tab's records as a dense table, grouped by day, each row opening its detail.
//
// One table component, four column sets: the Everything and Changes tabs say
// what happened and who did it; MCP calls name the agent, the server and tool,
// how long it took and how it went; the Daemon log shows level, logger and
// message. The first group line carries the list's summary on its right —
// "1 error and 1 warning in the last hour", "200 loaded of 1,204" — and on
// the MCP calls tab it names the window instead of the day (design 6.1).
// Selecting a row (click, Enter or Space) opens it in the drawer; on the
// Daemon log a row expands in place instead, under its own line (design
// 6.1.09).
import type { KeyboardEvent, ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { recordSeverity, type ActivityRecord, type ActivityTab } from "@/lib/activity/records";
import { dayLabel } from "@/lib/activity/recordText";
import { cn } from "@/lib/utils";
import { columnsFor } from "./activityColumns";
import type { AgentLook } from "./activityCells";

interface Props {
  tab: ActivityTab;
  rows: ActivityRecord[];
  agents: ReadonlyMap<string, AgentLook>;
  selectedKey: string | null;
  onSelect: (key: string) => void;
  /** The summary on the right of the first group line. */
  summary: ReactNode;
  /** On the MCP calls tab, the window the first group line names ("Last hour"). */
  windowLabel: string;
  /** The Daemon log row open in place, and what it shows. */
  renderExpanded?: (r: ActivityRecord) => ReactNode;
}

export function ActivityList({
  tab,
  rows,
  agents,
  selectedKey,
  onSelect,
  summary,
  windowLabel,
  renderExpanded,
}: Props) {
  const { t, i18n } = useTranslation();
  const columns = columnsFor(tab, t, agents);
  const now = new Date();
  // The Everything and Changes tabs group by day; the MCP calls tab and the
  // Daemon log mark only a day other than today, under the window line.
  const byDay = tab === "everything" || tab === "changes";
  const today = dayLabel(t, now.toISOString(), now, i18n.language);

  const onKey = (event: KeyboardEvent<HTMLTableRowElement>, key: string) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(key);
    }
  };

  // The line above the table: the first day (or the MCP calls tab's window)
  // with the list's summary. The Daemon log's own line (the file it reads) is
  // the page's, so the list draws none there.
  const firstDay = rows.length ? dayLabel(t, rows[0].at, now, i18n.language) : today;
  const caption = tab === "mcp" ? windowLabel : byDay ? firstDay : null;

  const body: ReactNode[] = [];
  let lastDay = byDay ? firstDay : today;
  for (const r of rows) {
    const day = dayLabel(t, r.at, now, i18n.language);
    if (day !== lastDay) {
      body.push(
        <tr key={`day:${day}:${r.key}`} aria-hidden>
          <td
            colSpan={columns.length}
            className="px-3 pb-1.5 pt-3 text-2xs font-semibold text-text-muted"
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
          "cursor-pointer border-b border-border-subtle outline-none transition-colors duration-fast",
          tab === "daemon" ? "h-8" : "h-[38px]",
          "hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring",
          selected && "bg-surface-selected hover:bg-surface-selected",
          selected && failing && "shadow-[inset_2px_0_0_rgb(var(--danger))]",
        )}
      >
        {columns.map((c) => (
          <td key={c.key} className={cn("max-w-0 px-3 align-middle", c.width)}>
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
          <td colSpan={columns.length} className="max-w-0 pb-3 pl-[120px] pr-3 pt-2.5">
            {expanded}
          </td>
        </tr>,
      );
    }
  }

  return (
    <>
      {caption !== null ? (
        <div className="flex items-center gap-2 px-3 pb-1.5 pt-2 text-2xs font-semibold text-text-muted">
          <span>{caption}</span>
          {summary ? (
            <span data-visual-volatile="count" className="ml-auto font-book">
              {summary}
            </span>
          ) : null}
        </div>
      ) : null}
      <table
        className="w-full min-w-[36rem] table-fixed border-collapse"
        aria-label={t(`activity.tabs.${tab}`)}
      >
        <thead>
          <tr className="h-control-md border-b border-border-subtle">
            {columns.map((c) => (
              <th
                key={c.key}
                scope="col"
                className={cn("px-3 text-left text-2xs font-semibold text-text-muted", c.width)}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        {/* Which records exist, and how many, changes from run to run; screenshot
          tests mask it and show a fixed number of rows. */}
        <tbody data-visual-volatile="rows">{body}</tbody>
      </table>
    </>
  );
}
