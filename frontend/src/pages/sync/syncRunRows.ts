// frontend/src/pages/sync/syncRunRows.ts
//
// What the Runs table renders: rounds, with stretches that say the same thing
// folded into a single row.
//
// A timer-driven history repeats itself. More than half of a converging
// vault's rounds changed nothing — 14 of 27 on the machine this was written
// against — and when something breaks it repeats even harder: an expired
// credential is ten identical failures by morning, a held round is re-raised
// every hour until someone answers it. One row each, they bury the rounds
// that actually said something, and they make a page whose whole job is to
// report a state read like an argument for it.
//
// They are not dropped, because they carry one thing nothing else does: a
// vault that STOPPED converging on Tuesday looks exactly like one that has had
// nothing to do, unless the repeats are there to show it kept trying. A folded
// row keeps that — it states the span and the count, so a gap reads as the
// distance between two folded rows rather than as something to reconstruct by
// scanning fourteen timestamps. The evidence survives; only the rows go.
//
// The newest round is never folded. It is the one the vault's current state is
// about and the one that may carry an answer, and a row you can act on has no
// business hiding inside a summary of its predecessors.
import type { RunRecord } from "@/lib/api/sync";

/** One row of the Runs table: a single round, or a stretch that repeated. */
export type SyncRunRow =
  | { kind: "run"; id: string; run: RunRecord }
  | { kind: "group"; id: string; status: string; runs: RunRecord[] };

/** Fewer than this and folding costs more than it saves: a lone round reads
 *  better as itself than as a group of one. */
const MIN_TO_FOLD = 2;

/**
 * The outcomes worth folding when they repeat.
 *
 * Not every status: a round that applied or published changes is a distinct
 * event however many like it came before, and `+3 ~1 −0` is not the same fact
 * twice. These three are. A quiet round says "nothing to do", a failure
 * repeats one broken thing every hour, and a held round is the same hold
 * re-raised until it is answered — none of which is more true for being
 * printed ten times.
 */
const FOLDABLE = new Set(["no_change", "failed", "awaiting_confirmation"]);

/**
 * A round with nothing to say.
 *
 * Deliberately stricter than `status === "no_change"`: a round can end
 * `no_change` and still have joined a remote, hit a failure, locked a
 * credential ref, or had an agent resolve a conflict. Each of those is
 * something a reader wants a row for. So the test is "this round's detail pane
 * would be empty", not "its badge says no change".
 */
export function isQuiet(run: RunRecord): boolean {
  return (
    run.status === "no_change" &&
    run.applied.changes.length === 0 &&
    run.published.changes.length === 0 &&
    run.conflicts.length === 0 &&
    run.agent_resolved.length === 0 &&
    run.failures.length === 0 &&
    run.locked_refs.length === 0 &&
    run.pending === null &&
    run.join === null &&
    !run.error
  );
}

/**
 * What a round is folded WITH — its status, or `null` when it stands alone.
 *
 * A quiet round is stricter than `status === "no_change"`: `isQuiet` refuses
 * any round whose detail pane would have something in it. Everything else
 * folds on the status alone, because two failures an hour apart with the same
 * outcome are the same news whatever their payloads say.
 */
function foldKey(run: RunRecord): string | null {
  if (run.status === "no_change") return isQuiet(run) ? "no_change" : null;
  return FOLDABLE.has(run.status) ? run.status : null;
}

/**
 * The history as rows, newest first, with consecutive like rounds folded.
 *
 * `runs` must arrive in the order the daemon returns it (newest first). The
 * fold is over ADJACENT rounds, so sorting beforehand would fold rounds that
 * were never consecutive in time — and the span a folded row reports would
 * then describe a stretch the vault did not actually spend that way.
 *
 * The first round is exempt. It is the present rather than the history: the
 * vault's current state is the state that round left, and it is the only one
 * that may carry Undo or an answer to a hold. Folding it away would hide the
 * row the page exists to offer.
 */
export function collapseRepeats(runs: RunRecord[]): SyncRunRow[] {
  const rows: SyncRunRow[] = [];
  let group: RunRecord[] = [];
  let key: string | null = null;

  const flush = () => {
    if (group.length === 0) return;
    if (group.length < MIN_TO_FOLD || key === null) {
      for (const run of group) rows.push({ kind: "run", id: String(run.id), run });
    } else {
      // Keyed on the newest member: stable across refetches, and unique
      // because a round belongs to exactly one fold.
      rows.push({ kind: "group", id: `group-${group[0].id}`, status: key, runs: group });
    }
    group = [];
    key = null;
  };

  runs.forEach((run, index) => {
    const runKey = index === 0 ? null : foldKey(run);
    if (runKey !== null && runKey === key) {
      group.push(run);
      return;
    }
    flush();
    if (runKey === null) {
      rows.push({ kind: "run", id: String(run.id), run });
      return;
    }
    key = runKey;
    group = [run];
  });
  flush();
  return rows;
}

/** The span a folded row reports: oldest start, newest finish, and how many. */
export function groupSpan(runs: RunRecord[]): { from: string; to: string; count: number } {
  // Newest-first, so the span runs from the LAST member's start to the FIRST
  // member's finish.
  return {
    from: runs[runs.length - 1].started_at,
    to: runs[0].finished_at,
    count: runs.length,
  };
}
