// frontend/src/pages/sync/syncRunRows.ts
//
// What the Runs table renders: rounds, with stretches that say the same thing
// folded into a single row.
//
// A timer-driven history repeats itself. Most rounds find nothing to do, and
// when something breaks it repeats harder: an expired secret is the same
// failure every pass until morning. One row each, they bury the rounds that
// said something. They are not dropped, because they carry one thing nothing
// else does: a vault that STOPPED syncing on Tuesday looks exactly like one
// with nothing to do, unless the repeats are there to show it kept trying. A
// folded row states its span and count, so the evidence survives and only the
// rows go.
//
// The newest round is never folded: it is the one the vault's current state is
// about, and a row you can act on has no business hiding inside a summary.
import type { SyncRound } from "@/lib/api/sync";

/** One row of the Runs table: a single round, or a stretch that repeated. */
export type SyncRunRow =
  | { kind: "run"; id: string; run: SyncRound }
  | { kind: "group"; id: string; status: string; runs: SyncRound[] };

/** Fewer than this and folding costs more than it saves. */
const MIN_TO_FOLD = 2;

/**
 * The outcomes worth folding when they repeat. Not the ones that moved files:
 * two rounds that each pulled three files are two events, not one fact twice.
 * These are the same situation re-reported until it changes.
 */
const FOLDABLE = new Set([
  "nothing_to_do",
  "unreachable",
  "auth_failed",
  "failed",
  "stopped",
  "held",
  "waiting_on_edit",
  "join_required",
  "paused_cloud_folder",
]);

/** A round with nothing to say: its detail pane would be empty. */
export function isQuiet(run: SyncRound): boolean {
  return (
    run.status === "nothing_to_do" &&
    run.pulled.length === 0 &&
    run.applied.length === 0 &&
    run.pushed.length === 0 &&
    !run.detail
  );
}

/** What a round is folded WITH — its status, or `null` when it stands alone. */
function foldKey(run: SyncRound): string | null {
  if (run.status === "nothing_to_do") return isQuiet(run) ? "nothing_to_do" : null;
  return FOLDABLE.has(run.status) ? run.status : null;
}

/** A row key: the round's id, or its finish time for a round never stored. */
function runKey(run: SyncRound): string {
  return run.id === null ? `at-${run.finished_at}` : String(run.id);
}

/**
 * The history as rows, newest first, with consecutive like rounds folded.
 * `runs` must arrive newest first, as the daemon returns them: the fold is
 * over ADJACENT rounds, so a sort beforehand would fold rounds that were never
 * consecutive in time.
 */
export function collapseRepeats(runs: SyncRound[]): SyncRunRow[] {
  const rows: SyncRunRow[] = [];
  let group: SyncRound[] = [];
  let key: string | null = null;

  const flush = () => {
    if (group.length === 0) return;
    if (group.length < MIN_TO_FOLD || key === null) {
      for (const run of group) rows.push({ kind: "run", id: runKey(run), run });
    } else {
      rows.push({ kind: "group", id: `group-${runKey(group[0])}`, status: key, runs: group });
    }
    group = [];
    key = null;
  };

  runs.forEach((run, index) => {
    const k = index === 0 ? null : foldKey(run);
    if (k !== null && k === key) {
      group.push(run);
      return;
    }
    flush();
    if (k === null) {
      rows.push({ kind: "run", id: runKey(run), run });
      return;
    }
    key = k;
    group = [run];
  });
  flush();
  return rows;
}

/** The span a folded row reports: oldest start, newest finish, and how many. */
export function groupSpan(runs: SyncRound[]): { from: string; to: string; count: number } {
  return {
    from: runs[runs.length - 1].started_at,
    to: runs[0].finished_at,
    count: runs.length,
  };
}
