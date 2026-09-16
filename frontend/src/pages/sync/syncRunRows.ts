// frontend/src/pages/sync/syncRunRows.ts
//
// What the Runs table renders: rounds, with runs of quiet ones folded into a
// single row.
//
// More than half of a converging vault's history is rounds that changed
// nothing — 14 of 27 on the machine this was written against. One row each,
// they bury the handful that did something or need an answer.
//
// They are not dropped, because they carry one thing nothing else does: a vault
// that STOPPED converging on Tuesday looks exactly like one that has had
// nothing to do, unless the quiet rounds are there to show it kept trying. A
// folded row keeps that — it states the span and the count, so a gap reads as
// the distance between two folded rows rather than as something to reconstruct
// by scanning fourteen timestamps. The evidence survives; only the rows go.
import type { RunRecord } from "@/lib/api/sync";

/** One row of the Runs table: a single round, or a run of quiet ones. */
export type SyncRunRow =
  | { kind: "run"; id: string; run: RunRecord }
  | { kind: "quiet"; id: string; runs: RunRecord[] };

/** Fewer than this and folding costs more than it saves: a lone quiet round
 *  reads better as itself than as a group of one. */
const MIN_TO_FOLD = 2;

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
 * The history as rows, newest first, with consecutive quiet rounds folded.
 *
 * `runs` must arrive in the order the daemon returns it (newest first). The
 * fold is over ADJACENT rounds, so sorting beforehand would fold rounds that
 * were never consecutive in time — and the span a folded row reports would
 * then describe a stretch the vault did not actually spend quiet.
 */
export function collapseQuietRounds(runs: RunRecord[]): SyncRunRow[] {
  const rows: SyncRunRow[] = [];
  let quiet: RunRecord[] = [];

  const flush = () => {
    if (quiet.length === 0) return;
    if (quiet.length < MIN_TO_FOLD) {
      for (const run of quiet) rows.push({ kind: "run", id: String(run.id), run });
    } else {
      // Keyed on the newest member: stable across refetches, and unique
      // because a round belongs to exactly one fold.
      rows.push({ kind: "quiet", id: `quiet-${quiet[0].id}`, runs: quiet });
    }
    quiet = [];
  };

  for (const run of runs) {
    if (isQuiet(run)) {
      quiet.push(run);
      continue;
    }
    flush();
    rows.push({ kind: "run", id: String(run.id), run });
  }
  flush();
  return rows;
}

/** The span a folded row reports: oldest start, newest finish, and how many. */
export function quietSpan(runs: RunRecord[]): { from: string; to: string; count: number } {
  // Newest-first, so the span runs from the LAST member's start to the FIRST
  // member's finish.
  return {
    from: runs[runs.length - 1].started_at,
    to: runs[0].finished_at,
    count: runs.length,
  };
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
 * Lives here beside `heldRoundId` because the two answer one question —
 * WHICH row may act — for two routes that share the same shape: neither names
 * a round, so the surface has to name it for them.
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
 * The id of the one round that may carry the held-round actions, or null.
 *
 * Two conditions, and the second is the one that was missing. `POST
 * /sync/confirm` acts on the vault's CURRENT pending state, not on a round
 * named in the request — so a row may offer it only while the vault is
 * actually waiting. Older rows keep `awaiting_confirmation` as their outcome
 * forever: the timer re-raises one held situation as a new round every pass,
 * and answering it produces a FURTHER round rather than rewriting the ones
 * that were held. Ungated, each of those historical rows would show a
 * live-looking call to action that does nothing a reader could predict.
 *
 * @param runs    the history, newest first.
 * @param waiting whether `/sync/status` reports a pending confirmation NOW.
 */
export function heldRoundId(runs: RunRecord[], waiting: boolean): number | null {
  if (!waiting) return null;
  const newest = runs[0];
  return newest && newest.status === "awaiting_confirmation" ? newest.id : null;
}
