// src/components/activity/ActivityList.tsx — the visible tab's records as a dense table, grouped by day, each row opening its detail.
//
// One table component, four column sets: the Everything and Changes tabs say
// what happened and who did it; MCP calls name the agent, the server and tool,
// how long it took and how it went; the Daemon log shows level, logger and
// message. Selecting a row (click, Enter or Space) opens it in the drawer.
import type { KeyboardEvent, ReactNode } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { describeDaemonRecord } from "@/lib/activity/activityText";
import { recordLogger, type ActivityRecord, type ActivityTab } from "@/lib/activity/records";
import { dayLabel } from "@/lib/activity/recordText";
import { cn } from "@/lib/utils";
import {
  ByCell,
  CallStatus,
  CallTarget,
  EventCell,
  LevelWord,
  SourceIcon,
  TimeCell,
  TookCell,
  type AgentLook,
} from "./activityCells";

interface Column {
  key: string;
  header: string;
  /** Tailwind width class for the column. */
  width?: string;
  cell: (r: ActivityRecord) => ReactNode;
}

function columnsFor(
  tab: ActivityTab,
  t: TFunction,
  agents: ReadonlyMap<string, AgentLook>,
): Column[] {
  const time: Column = {
    key: "time",
    header: t("activity.table.time"),
    width: tab === "daemon" ? "w-28" : "w-20",
    cell: (r) => <TimeCell at={r.at} withMs={tab === "daemon"} />,
  };
  if (tab === "mcp") {
    return [
      time,
      {
        key: "agent",
        header: t("activity.table.agent"),
        width: "w-36",
        cell: (r) => {
          if (r.source !== "call") return null;
          const agent = r.call.agent_uid ? agents.get(r.call.agent_uid) : undefined;
          return agent ? (
            <AgentBadge type={agent.type} name={agent.name} size="sm" showName tooltip={false} />
          ) : (
            <span className="text-xs text-text-subtle">—</span>
          );
        },
      },
      {
        key: "target",
        header: t("activity.table.serverTool"),
        cell: (r) => (r.source === "call" ? <CallTarget call={r.call} /> : null),
      },
      {
        key: "took",
        header: t("activity.table.took"),
        width: "w-20",
        cell: (r) => <TookCell record={r} />,
      },
      {
        key: "status",
        header: t("activity.table.status"),
        width: "w-24",
        cell: (r) => (r.source === "call" ? <CallStatus t={t} call={r.call} /> : null),
      },
    ];
  }
  if (tab === "daemon") {
    return [
      time,
      {
        key: "level",
        header: t("activity.table.level"),
        width: "w-20",
        cell: (r) => <LevelWord record={r} />,
      },
      {
        key: "logger",
        header: t("activity.table.logger"),
        width: "w-40",
        cell: (r) => (
          <span className="block truncate font-mono text-xs text-text-muted">
            {recordLogger(r) || "—"}
          </span>
        ),
      },
      {
        key: "message",
        header: t("activity.table.message"),
        cell: (r) =>
          r.source === "daemon" ? (
            <span className="block truncate font-mono text-xs text-text">
              {describeDaemonRecord(t, r.log)}
            </span>
          ) : null,
      },
    ];
  }
  const columns: Column[] = [
    time,
    { key: "icon", header: "", width: "w-8", cell: (r) => <SourceIcon record={r} /> },
    {
      key: "event",
      header: t("activity.table.event"),
      cell: (r) => <EventCell t={t} record={r} />,
    },
    {
      key: "by",
      header: t("activity.table.by"),
      width: "w-24",
      cell: (r) => <ByCell t={t} record={r} agents={agents} />,
    },
  ];
  if (tab === "everything") {
    columns.push({
      key: "took",
      header: t("activity.table.took"),
      width: "w-16",
      cell: (r) => <TookCell record={r} />,
    });
  }
  return columns;
}

interface Props {
  tab: ActivityTab;
  rows: ActivityRecord[];
  agents: ReadonlyMap<string, AgentLook>;
  selectedKey: string | null;
  onSelect: (key: string) => void;
}

export function ActivityList({ tab, rows, agents, selectedKey, onSelect }: Props) {
  const { t, i18n } = useTranslation();
  const columns = columnsFor(tab, t, agents);
  const now = new Date();

  const onKey = (event: KeyboardEvent<HTMLTableRowElement>, key: string) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(key);
    }
  };

  const body: ReactNode[] = [];
  let lastDay = "";
  for (const r of rows) {
    const day = dayLabel(t, r.at, now, i18n.language);
    if (day !== lastDay) {
      lastDay = day;
      body.push(
        <tr key={`day:${day}:${r.key}`} aria-hidden>
          <td
            colSpan={columns.length}
            className="px-3 pb-1 pt-3 text-2xs font-semibold text-text-muted"
          >
            {day}
          </td>
        </tr>,
      );
    }
    const selected = r.key === selectedKey;
    body.push(
      <tr
        key={r.key}
        tabIndex={0}
        aria-selected={selected}
        data-record={r.key}
        onClick={() => onSelect(r.key)}
        onKeyDown={(e) => onKey(e, r.key)}
        className={cn(
          "h-[38px] cursor-pointer border-b border-border-subtle outline-none transition-colors duration-fast",
          "hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring",
          selected && "bg-surface-selected hover:bg-surface-selected",
        )}
      >
        {columns.map((c) => (
          <td key={c.key} className={cn("max-w-0 px-3 align-middle", c.width)}>
            {c.cell(r)}
          </td>
        ))}
      </tr>,
    );
  }

  return (
    <table
      className="w-full min-w-[36rem] table-fixed border-collapse"
      aria-label={t(`activity.tabs.${tab}`)}
    >
      <thead>
        <tr className="h-[30px] border-b border-border-subtle">
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
      {/* Which records exist changes from run to run; screenshot tests mask it. */}
      <tbody data-visual-volatile>{body}</tbody>
    </table>
  );
}
