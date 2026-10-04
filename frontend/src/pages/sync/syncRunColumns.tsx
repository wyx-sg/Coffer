// frontend/src/pages/sync/syncRunColumns.tsx
//
// The Rounds table's columns (6.4.01): when a round finished, how it ended
// (a dot and a word, then the clause that tells it apart), and how many files
// it pulled and pushed. Pulled and pushed are two columns and not one, because
// they are different facts: a machine that pushes every round and pulls nothing
// is the one everybody else is following. There is no Commits column and no
// Roll back on a row — the commits are in the round's drawer, and so is the
// only Roll back.
//
// A folded row states its outcome once with its count ("Nothing to do ×6")
// and its span in the When column; it moved nothing by construction, so its
// number cells stay empty.
import type { TFunction } from "i18next";

import type { Column } from "@/components/DataTable";
import type { SyncRound } from "@/lib/api/sync";
import { SyncRoundOutcome as Outcome } from "./SyncRoundOutcome";
import { movedCells, outcomeLabel, roundLabel } from "./syncRoundLabel";
import { groupSpan, type SyncRunRow } from "./syncRunRows";
import { dayTime, daySpan } from "./syncTime";

interface Context {
  runs: SyncRound[];
  nextRoundAt: string | null;
}

const NUM = "w-20 whitespace-nowrap text-right text-xs text-text-muted";

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
  ];
}
