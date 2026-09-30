// src/components/activity/activityColumns.tsx — the columns of each Activity tab's table.
//
// Everything and Changes say what happened and who did it (Everything adds
// how long a call took); MCP calls name the agent, the server and tool, how
// long it took and how it went; the Daemon log shows level, logger and
// message. Widths follow design 6.1 and include each cell's 12px padding.
import type { ReactNode } from "react";
import type { TFunction } from "i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
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
  LevelChip,
  SourceIcon,
  TimeCell,
  TookCell,
  type AgentLook,
} from "./activityCells";

/** @ui-only One column of an Activity table. */
export interface Column {
  key: string;
  header: string;
  /** Tailwind width class for the column (its 12px padding included). */
  width?: string;
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
    width: tab === "daemon" ? "w-[120px]" : "w-[88px]",
    cell: (r) => <TimeCell at={r.at} withMs={tab === "daemon"} />,
  };
  if (tab === "mcp") {
    return [
      time,
      {
        key: "agent",
        header: t("activity.table.agent"),
        width: "w-[134px]",
        cell: (r) => {
          if (r.source !== "call") return null;
          const agent = r.call.agent_uid ? agents.get(r.call.agent_uid) : undefined;
          return agent ? (
            <span className="flex min-w-0 items-center gap-1.5">
              <AgentBadge type={agent.type} name={agent.name} size="sm" tooltip={false} />
              <span className="truncate text-xs text-text-muted">{agent.name}</span>
            </span>
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
        width: "w-[84px]",
        cell: (r) => <TookCell record={r} />,
      },
      {
        key: "status",
        header: t("activity.table.status"),
        width: "w-[96px]",
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
        width: "w-[100px]",
        cell: (r) => <LevelChip record={r} />,
      },
      {
        key: "logger",
        header: t("activity.table.logger"),
        width: "w-[160px]",
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
    { key: "icon", header: "", width: "w-[46px]", cell: (r) => <SourceIcon record={r} /> },
    {
      key: "event",
      header: t("activity.table.event"),
      cell: (r) => <EventCell t={t} record={r} />,
    },
    {
      key: "by",
      header: t("activity.table.by"),
      width: "w-[84px]",
      cell: (r) => <ByCell t={t} record={r} agents={agents} />,
    },
  ];
  if (tab === "everything") {
    columns.push({
      key: "took",
      header: t("activity.table.took"),
      width: "w-[80px]",
      cell: (r) => <TookCell record={r} />,
    });
  }
  return columns;
}
