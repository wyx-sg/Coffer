// frontend/src/pages/activity/daemonColumns.tsx
//
// The Daemon tab's columns — its own, not a shape shared with the other two
// records: a log line has a level and a logger, and nothing else here does.
// Split out of the tab so the tab stays a tab (query, filters, states) rather
// than also being a renderer.
import type { TFunction } from "i18next";
import { Badge } from "@/components/ui/badge";
import type { Column } from "@/components/DataTable";
import { toneClass, type Tone } from "@/lib/statusColors";
import { formatDateTime } from "@/lib/utils";
import { daemonLogger, describeDaemonRecord } from "./activityText";
import type { components } from "@/lib/api/types";

type DaemonLogRecord = components["schemas"]["DaemonLogRecordOut"];

/** A structlog level in the badge vocabulary the rest of the app uses. */
const LEVEL_TONE: Record<string, Tone> = {
  critical: "error",
  exception: "error",
  error: "error",
  warning: "warn",
  warn: "warn",
};

export interface DaemonRow {
  /** Position in the fetched tail — the route returns no id. */
  id: string;
  rec: DaemonLogRecord;
  /** null when nothing in the payload said when; the cell renders a dash. */
  at: string | null;
}

export function daemonColumns(t: TFunction): Column<DaemonRow>[] {
  return [
    {
      key: "time",
      header: t("activity.daemon.table.time"),
      className: "w-44 whitespace-nowrap text-xs text-muted-foreground",
      // A dash, never the epoch: a row must not claim a time it does not have.
      cell: (row) => (row.at ? formatDateTime(row.at) : "—"),
    },
    {
      key: "level",
      header: t("activity.daemon.table.level"),
      className: "w-24",
      cell: (row) => {
        // A line that never parsed as JSON carries no level; say so with the
        // same dash, rather than inventing a severity for it.
        const level = row.rec.level;
        if (!level) return "—";
        const tone = LEVEL_TONE[level.toLowerCase()];
        return (
          <Badge variant="outline" className={tone ? toneClass(tone) : undefined}>
            {level}
          </Badge>
        );
      },
    },
    {
      key: "logger",
      header: t("activity.daemon.table.logger"),
      className: "w-48 break-words font-mono text-xs text-muted-foreground",
      cell: (row) => daemonLogger(row.rec) || "—",
    },
    {
      key: "message",
      header: t("activity.daemon.table.message"),
      // A traceback line arrives verbatim and can be long; wrap rather than
      // truncate, so the failure is readable without expanding the row.
      className: "text-sm break-words",
      cell: (row) => describeDaemonRecord(t, row.rec),
    },
  ];
}
