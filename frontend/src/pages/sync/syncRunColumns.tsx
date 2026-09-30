// frontend/src/pages/sync/syncRunColumns.tsx
//
// The Runs table's columns — what one round produces: when it ran, how it
// ended, how many files it pulled and pushed, and the commits it moved the
// vault between. Pulled and pushed are two columns and not one, because they
// are different facts: a machine that pushes every round and pulls nothing is
// the one everybody else is following.
//
// Split out of the tab so the tab stays a tab (query, filters, states) rather
// than also being a renderer.
import type { TFunction } from "i18next";

import { Badge } from "@/components/ui/badge";
import type { Column } from "@/components/DataTable";
import { toneClass } from "@/lib/statusColors";
import { formatDateTime } from "@/lib/utils";
import { SyncRollbackAction } from "./SyncRollbackAction";
import { canRollBack } from "./syncRowActions";
import { statusLabel, statusTone } from "./syncRoundStatus";
import { groupSpan, type SyncRunRow } from "./syncRunRows";

/** The status a folded row answers the filter with: every round inside it
 *  ended the same way, which is what let them fold at all. */
export function rowStatus(row: SyncRunRow): string {
  return row.kind === "group" ? row.status : row.run.status;
}

const short = (sha: string | null) => (sha ? sha.slice(0, 7) : "—");

export function syncRunColumns(t: TFunction): Column<SyncRunRow>[] {
  return [
    {
      key: "when",
      header: t("sync.runs.table.when"),
      className: "w-44 text-xs text-muted-foreground",
      // When it FINISHED: the moment the vault and the remote were last in the
      // state this row describes. A folded row reports its stretch instead.
      cell: (row) => {
        if (row.kind === "run") return formatDateTime(row.run.finished_at);
        const span = groupSpan(row.runs);
        return (
          <span className="whitespace-nowrap">
            {formatDateTime(span.from)} → {formatDateTime(span.to)}
          </span>
        );
      },
    },
    {
      key: "status",
      header: t("sync.runs.table.status"),
      className: "w-52",
      cell: (row) => (
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="outline" className={toneClass(statusTone(rowStatus(row)))}>
            {statusLabel(t, rowStatus(row))}
          </Badge>
          {row.kind === "group" ? (
            <Badge variant="outline" className={toneClass("muted")}>
              {t("sync.runs.folded", { count: row.runs.length })}
            </Badge>
          ) : null}
        </div>
      ),
    },
    {
      key: "pulled",
      header: t("sync.runs.table.pulled"),
      className: "w-24 text-xs",
      // A folded row moved nothing by construction, so it shows the dash an
      // absent value shows rather than a zero repeated N times.
      cell: (row) => (row.kind === "run" ? row.run.pulled_files : "—"),
    },
    {
      key: "pushed",
      header: t("sync.runs.table.pushed"),
      className: "w-24 text-xs",
      cell: (row) => (row.kind === "run" ? row.run.pushed_files : "—"),
    },
    {
      key: "commits",
      header: t("sync.runs.table.commits"),
      className: "w-40 whitespace-nowrap font-mono text-xs text-muted-foreground",
      // A dash, never a blank: a round that moved the vault nowhere is saying
      // something, not missing a value.
      cell: (row) => {
        if (row.kind !== "run" || (!row.run.from_commit && !row.run.to_commit)) return "—";
        return `${short(row.run.from_commit)}..${short(row.run.to_commit)}`;
      },
    },
    {
      key: "actions",
      header: "",
      className: "w-40 text-right",
      cell: (row) =>
        row.kind === "run" && canRollBack(row.run) ? <SyncRollbackAction run={row.run} /> : null,
    },
  ];
}
