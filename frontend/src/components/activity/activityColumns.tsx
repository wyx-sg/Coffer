// src/components/activity/activityColumns.tsx — the columns of each Activity tab's table.
//
// Design 6.2.01, 6.2.07, 6.2.08, 6.2.10. Everything: Time 76 · icon 26 · Event
// · By 110 · Took 64. Changes: Time · icon · Change · By. Tool calls: Time ·
// Agent · `server.`(grey)+tool · Took (right-aligned, sortable) · Status. The
// Daemon log: Time · Level · Logger · Message. Each width is the column's
// content width; the table adds 5px either side of every cell (10px between
// columns) and 12px at the box's edges.
import type { ReactNode } from "react";
import type { TFunction } from "i18next";

import { describeDaemonRecord } from "@/lib/activity/activityText";
import {
  recordLogger,
  recordSeverity,
  type ActivityRecord,
  type ActivityTab,
} from "@/lib/activity/records";
import { cn } from "@/lib/utils";
import {
  ByCell,
  CallStatus,
  CallTarget,
  EventCell,
  LevelText,
  SourceIcon,
  TimeCell,
  TookCell,
  type AgentLook,
} from "./activityCells";

/** @ui-only One column of an Activity table. */
export interface Column {
  key: string;
  header: string;
  /** Content width in px; the last flexible column leaves it out. */
  width?: number;
  align?: "right";
  /** The header sorts the loaded rows (numbers only). */
  sortable?: boolean;
  cell: (r: ActivityRecord) => ReactNode;
}

export function columnsFor(
  tab: ActivityTab,
  t: TFunction,
  agents: ReadonlyMap<string, AgentLook>,
): Column[] {
  const time: Column = {
    key: "time",
    header: t("activity.table.time"),
    width: tab === "daemon" ? 96 : 76,
    cell: (r) => <TimeCell at={r.at} withMs={tab === "daemon"} />,
  };
  if (tab === "mcp") {
    return [
      time,
      {
        key: "agent",
        header: t("activity.table.agent"),
        width: 120,
        cell: (r) => {
          if (r.source !== "call") return null;
          const agent = r.call.agent_uid ? agents.get(r.call.agent_uid) : undefined;
          return agent ? (
            <span className="block truncate text-xs text-text">{agent.name}</span>
          ) : (
            <span className="text-xs text-text-subtle">—</span>
          );
        },
      },
      {
        key: "target",
        header: t("activity.table.serverTool"),
        cell: (r) => (r.source === "call" ? <CallTarget call={r.call} muteServer /> : null),
      },
      {
        key: "took",
        header: t("activity.table.took"),
        width: 72,
        align: "right",
        sortable: true,
        cell: (r) => <TookCell record={r} />,
      },
      {
        key: "status",
        header: t("activity.table.status"),
        width: 84,
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
        width: 64,
        cell: (r) => <LevelText record={r} />,
      },
      {
        key: "logger",
        header: t("activity.table.logger"),
        width: 140,
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
            <span
              className={cn(
                "block truncate font-mono text-xs",
                recordSeverity(r) === "error" ? "text-danger" : "text-text",
              )}
            >
              {describeDaemonRecord(t, r.log)}
            </span>
          ) : null,
      },
    ];
  }
  const columns: Column[] = [
    time,
    { key: "icon", header: "", width: 26, cell: (r) => <SourceIcon record={r} /> },
    {
      key: "event",
      header: t(tab === "changes" ? "activity.table.change" : "activity.table.event"),
      cell: (r) => <EventCell t={t} record={r} />,
    },
    {
      key: "by",
      header: t("activity.table.by"),
      width: 110,
      cell: (r) => <ByCell t={t} record={r} agents={agents} />,
    },
  ];
  if (tab === "everything") {
    columns.push({
      key: "took",
      header: t("activity.table.took"),
      width: 64,
      align: "right",
      cell: (r) => <TookCell record={r} />,
    });
  }
  return columns;
}
