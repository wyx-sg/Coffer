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
import { SyncRollbackAction } from "./SyncRollbackAction";

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

/** What a free-text search on a history row matches against. */
export function runSearchHaystack(t: TFunction, run: RunRecord): string {
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

/**
 * Statuses that prove a round reached step 4 and tagged a pre-apply snapshot
 * (`convergence.py` `--- 4 guard + snapshot ---`): it applied, or it had
 * nothing to apply, or it applied here and only the push failed.
 */
const SNAPSHOTTED = new Set(["ok", "no_change", "push_failed"]);

/**
 * Statuses that prove a round stopped BEFORE the snapshot — a conflict stops
 * at the merge, a held round at the guard, and a disabled one never ran. Such
 * a round left no snapshot, so the round underneath it is still the one a
 * rollback undoes.
 */
const PRE_SNAPSHOT = new Set(["conflict", "awaiting_confirmation", "disabled"]);

/**
 * The id of the one round `POST /sync/rollback` would undo, or null.
 *
 * The route takes no argument: it reverses the round that left the NEWEST
 * pre-apply snapshot. So the surface has to work out which row that is rather
 * than offering the same call from every row under a different name.
 *
 * `failed` deliberately ends the walk with no target. A failed round may have
 * died before the snapshot or after it — the status cannot say which — and
 * guessing the wrong way would put "Undo" on a round that is not the one the
 * daemon would reverse. No button is the honest answer; `coffer sync rollback`
 * is still there for someone who knows what happened.
 *
 * @param runs the history, newest first, exactly as the daemon returns it.
 */
export function rollbackTargetId(runs: RunRecord[]): number | null {
  for (const run of runs) {
    if (SNAPSHOTTED.has(run.status)) return run.id;
    if (!PRE_SNAPSHOT.has(run.status)) return null;
  }
  return null;
}

/**
 * @param rollbackTarget the id from `rollbackTargetId` — the single row that
 *   carries the Undo action, or null when no round can be undone.
 */
export function syncRunColumns(t: TFunction, rollbackTarget: number | null): Column<RunRecord>[] {
  return [
    {
      key: "when",
      header: t("sync.history.table.when"),
      className: "w-44 whitespace-nowrap text-xs text-muted-foreground",
      // When it FINISHED, not when it started: that is the moment the vault
      // and the remote were last in the state this row describes.
      cell: (run) => formatDateTime(run.finished_at),
    },
    {
      key: "outcome",
      header: t("sync.history.table.outcome"),
      className: "w-52",
      cell: (run) => (
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="outline" className={toneClass(STATUS_TONE[run.status] ?? "muted")}>
            {statusLabel(t, run.status)}
          </Badge>
          {/* A join is the one thing about a round that is not in its counts:
              the same "322 published" means something entirely different on
              the round where this machine first met the remote. */}
          {run.join ? (
            <Badge variant="outline" className={toneClass("muted")}>
              {t(`sync.history.joinShort.${run.join}`)}
            </Badge>
          ) : null}
        </div>
      ),
    },
    {
      key: "applied",
      header: t("sync.history.table.applied"),
      className: "w-40 whitespace-nowrap text-xs",
      cell: (run) => countsLabel(t, run.applied),
    },
    {
      key: "published",
      header: t("sync.history.table.published"),
      className: "w-40 whitespace-nowrap text-xs",
      cell: (run) => countsLabel(t, run.published),
    },
    {
      key: "commit",
      header: t("sync.history.table.commit"),
      className: "w-28 font-mono text-xs text-muted-foreground",
      // A dash, never a blank: a round that landed no commit (nothing changed,
      // or it never got that far) is saying something, not missing a value.
      cell: (run) => (run.commit ? run.commit.slice(0, 10) : "—"),
    },
    {
      key: "undo",
      // No header text: one action on one row, and a column heading over
      // mostly-empty cells reads as a value that is missing everywhere else.
      header: "",
      className: "w-36 text-right",
      cell: (run) => (run.id === rollbackTarget ? <SyncRollbackAction run={run} /> : null),
    },
  ];
}
