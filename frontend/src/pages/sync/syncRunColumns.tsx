// frontend/src/pages/sync/syncRunColumns.tsx
//
// The Rounds table's columns (6.5.01): when a round finished, how it ended
// (a dot and a word, then the clause that tells it apart), how many files it
// pulled and pushed, the commits it moved the vault between, and Roll back on
// the rounds that can be rolled back. Pulled and pushed are two columns and
// not one, because they are different facts: a machine that pushes every
// round and pulls nothing is the one everybody else is following.
//
// A folded row states its outcome once with its count ("Nothing to do ×6")
// and its span in the When column; it moved nothing by construction, so its
// number cells stay empty.
import type { TFunction } from "i18next";
import { Undo2 } from "lucide-react";

import type { Column } from "@/components/DataTable";
import { TableActionButton } from "@/components/table/TableActionButton";
import type { SyncRound } from "@/lib/api/sync";
import { SyncRoundOutcome as Outcome } from "./SyncRoundOutcome";
import { canRollBack } from "./syncRowActions";
import { commitsCell, movedCells, outcomeLabel, roundLabel } from "./syncRoundLabel";
import { groupSpan, type SyncRunRow } from "./syncRunRows";
import { dayTime, daySpan } from "./syncTime";

interface Context {
  runs: SyncRound[];
  nextRoundAt: string | null;
  onRollback: (run: SyncRound & { id: number }) => void;
}

const NUM = "w-16 whitespace-nowrap font-mono text-xs text-text-muted";

export function syncRunColumns(t: TFunction, ctx: Context): Column<SyncRunRow>[] {
  const newestId = (() => {
    const first = ctx.runs[0];
    return first ? (first.id === null ? `at-${first.finished_at}` : String(first.id)) : null;
  })();
  return [
    {
      key: "when",
      header: t("sync.rounds.columns.when"),
      className: "w-44 whitespace-nowrap text-xs",
      cell: (row) => {
        if (row.kind === "run") {
          return <span className="text-text">{dayTime(row.run.finished_at, t)}</span>;
        }
        const span = groupSpan(row.runs);
        return <span className="text-text-muted">{daySpan(span.from, span.to, t)}</span>;
      },
    },
    {
      key: "round",
      header: t("sync.rounds.columns.round"),
      className: "min-w-0",
      cell: (row) => {
        if (row.kind === "group") {
          return (
            <Outcome
              status={row.status}
              main={t("sync.rounds.folded", {
                label: outcomeLabel(t, row.status),
                count: row.runs.length,
              })}
              detail={null}
            />
          );
        }
        const label = roundLabel(t, row.run, {
          runs: ctx.runs,
          newest: row.id === newestId,
          nextRoundAt: ctx.nextRoundAt,
        });
        return <Outcome status={row.run.status} main={label.main} detail={label.detail} />;
      },
    },
    {
      key: "pulled",
      header: t("sync.rounds.columns.pulled"),
      className: NUM,
      cell: (row) => (row.kind === "run" ? movedCells(row.run).pulled : null),
    },
    {
      key: "pushed",
      header: t("sync.rounds.columns.pushed"),
      className: NUM,
      cell: (row) => (row.kind === "run" ? movedCells(row.run).pushed : null),
    },
    {
      key: "commits",
      header: t("sync.rounds.columns.commits"),
      className: "w-40 whitespace-nowrap font-mono text-xs text-text-muted",
      cell: (row) => (row.kind === "run" ? commitsCell(row.run) : null),
    },
    {
      key: "actions",
      header: "",
      className: "w-28 text-right",
      cell: (row) =>
        row.kind === "run" && canRollBack(row.run) ? (
          <TableActionButton
            icon={Undo2}
            label={t("sync.rollback.action")}
            onClick={() => ctx.onRollback(row.run as SyncRound & { id: number })}
          />
        ) : null,
    },
  ];
}
