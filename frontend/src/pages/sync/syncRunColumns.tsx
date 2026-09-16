// frontend/src/pages/sync/syncRunColumns.tsx
//
// The History tab's columns — the five things one converge round actually
// produces: when it ran, how it ended, what it applied to this vault, what it
// published to the remote, and the commit it landed on.
//
// Applied and published are two columns and not one, because the whole point
// of bidirectional convergence is that they are different numbers: a machine
// that publishes every round and applies nothing is coming from somewhere, and
// one that applies every round and publishes nothing is going somewhere.
//
// Split out of the tab so the tab stays a tab (query, filters, states) rather
// than also being a renderer — the same seam the Activity page's Daemon tab
// takes.
import type { TFunction } from "i18next";
import { Badge } from "@/components/ui/badge";
import type { Column } from "@/components/DataTable";
import type { DiffCounts, RunRecord } from "@/lib/api/sync";
import { toneClass, type Tone } from "@/lib/statusColors";
import { formatDateTime } from "@/lib/utils";
import { SyncHeldRoundActions } from "./SyncHeldRoundActions";
import { SyncRollbackAction } from "./SyncRollbackAction";
import { quietSpan, type SyncRunRow } from "./syncRunRows";

/**
 * A round's status in the badge vocabulary the rest of the app uses.
 *
 * `no_change` is `muted` rather than `ok` on purpose: it succeeded, but a wall
 * of green for rounds that did nothing would drown the ones that did.
 * `push_failed` is a warning and not an error — everything applied here and
 * the commit is waiting, which is a different situation from a round that
 * failed outright.
 */
const STATUS_TONE: Record<string, Tone> = {
  ok: "ok",
  no_change: "muted",
  conflict: "warn",
  awaiting_confirmation: "warn",
  push_failed: "warn",
  failed: "error",
  disabled: "muted",
};

/** A round's status as a word, falling back to the wire value verbatim. */
export function statusLabel(t: TFunction, status: string): string {
  return t(`sync.round.statusLabel.${status}`, { defaultValue: status });
}

/** `+2 ~1 −0`, in the same order the counts are reported everywhere else. */
function countsLabel(t: TFunction, counts: DiffCounts): string {
  return t("sync.history.countsShort", { ...counts });
}

/** What a free-text search matches against, for either kind of row.
 *
 * A folded row answers for the stretch it stands in for — its own span and the
 * words "no change" — not its members' fields. Searching for a commit should
 * not surface a fold that merely contains one, because the fold does not show
 * it and clicking it would not reveal it. */
export function rowSearchHaystack(t: TFunction, row: SyncRunRow): string {
  if (row.kind === "quiet") {
    const span = quietSpan(row.runs);
    return [formatDateTime(span.from), formatDateTime(span.to), statusLabel(t, "no_change")]
      .join(" ")
      .toLowerCase();
  }
  return runSearchHaystack(t, row.run);
}

/** What a free-text search on one round matches against. Not exported: every
 *  caller goes through `rowSearchHaystack`, which knows about folds too, and a
 *  second entry point is how a search that ignores them creeps back. */
function runSearchHaystack(t: TFunction, run: RunRecord): string {
  return [
    formatDateTime(run.finished_at),
    statusLabel(t, run.status),
    run.status,
    run.join ?? "",
    run.commit ?? "",
    ...run.conflicts,
    ...run.agent_resolved,
    ...run.locked_refs,
    ...run.failures.map((f) => `${f.path} ${f.reason}`),
    run.error ?? "",
  ]
    .join(" ")
    .toLowerCase();
}

/** The status a folded row answers the filter with: every round inside it
 *  ended `no_change`, so filtering to that outcome should find it. */
export function rowStatus(row: SyncRunRow): string {
  return row.kind === "quiet" ? "no_change" : row.run.status;
}

interface ColumnArgs {
  /** From `rollbackTargetId` — the single round that carries Undo, or null. */
  rollbackTarget: number | null;
  /** From `heldRoundId` — the single round that carries the held-round
   *  answers, or null when the vault is not waiting on one. */
  heldTarget: number | null;
}

export function syncRunColumns(t: TFunction, args: ColumnArgs): Column<SyncRunRow>[] {
  const { rollbackTarget, heldTarget } = args;
  return [
    {
      key: "when",
      header: t("sync.history.table.when"),
      className: "w-44 text-xs text-muted-foreground",
      // When it FINISHED, not when it started: that is the moment the vault
      // and the remote were last in the state this row describes. A folded row
      // reports its stretch instead, which is the whole reason it is allowed
      // to stand in for its members: a gap in convergence then reads as the
      // distance between two spans rather than as fourteen timestamps to scan.
      cell: (row) => {
        if (row.kind === "run") return formatDateTime(row.run.finished_at);
        const span = quietSpan(row.runs);
        return (
          <span className="whitespace-nowrap">
            {formatDateTime(span.from)} → {formatDateTime(span.to)}
          </span>
        );
      },
    },
    {
      key: "outcome",
      header: t("sync.history.table.outcome"),
      className: "w-52",
      cell: (row) => (
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="outline" className={toneClass(STATUS_TONE[rowStatus(row)] ?? "muted")}>
            {statusLabel(t, rowStatus(row))}
          </Badge>
          {row.kind === "quiet" ? (
            <Badge variant="outline" className={toneClass("muted")}>
              {t("sync.runs.folded", { count: row.runs.length })}
            </Badge>
          ) : null}
          {/* A join is the one thing about a round that is not in its counts:
              the same "322 published" means something entirely different on
              the round where this machine first met the remote. */}
          {row.kind === "run" && row.run.join ? (
            <Badge variant="outline" className={toneClass("muted")}>
              {t(`sync.history.joinShort.${row.run.join}`)}
            </Badge>
          ) : null}
        </div>
      ),
    },
    {
      key: "applied",
      header: t("sync.history.table.applied"),
      className: "w-40 whitespace-nowrap text-xs",
      // A folded row moved nothing by construction, so it shows the dash an
      // absent value shows rather than a tally of zeroes repeated N times.
      cell: (row) => (row.kind === "run" ? countsLabel(t, row.run.applied) : "—"),
    },
    {
      key: "published",
      header: t("sync.history.table.published"),
      className: "w-40 whitespace-nowrap text-xs",
      cell: (row) => (row.kind === "run" ? countsLabel(t, row.run.published) : "—"),
    },
    {
      key: "commit",
      header: t("sync.history.table.commit"),
      className: "w-28 font-mono text-xs text-muted-foreground",
      // A dash, never a blank: a round that landed no commit (nothing changed,
      // or it never got that far) is saying something, not missing a value.
      cell: (row) => (row.kind === "run" && row.run.commit ? row.run.commit.slice(0, 10) : "—"),
    },
    {
      key: "actions",
      // No header text: at most one row carries anything here, and a column
      // heading over mostly-empty cells reads as a value that is missing
      // everywhere else.
      header: "",
      className: "w-64 text-right",
      cell: (row) => {
        if (row.kind !== "run") return null;
        // A held round's answers outrank Undo — there is nothing to undo yet,
        // and the round is waiting on the reader. Each is gated on its own
        // single target, so in practice the two never land on one row.
        if (row.run.id === heldTarget && row.run.pending) {
          return <SyncHeldRoundActions pending={row.run.pending} />;
        }
        return row.run.id === rollbackTarget ? <SyncRollbackAction run={row.run} /> : null;
      },
    },
  ];
}
