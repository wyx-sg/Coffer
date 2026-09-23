// frontend/src/pages/sync/syncRowActions.ts
//
// Which row of the Runs table may act, for the two routes that name no round.
//
// `POST /sync/rollback` reverses the newest pre-apply snapshot and
// `POST /sync/confirm` answers the vault's current pending state — neither
// takes an id. So the surface has to work out which single row honestly
// carries each action, rather than offering the same call from every row
// under a different name. Split out of `syncRunRows.ts`, which answers a
// different question (which rows are one row) and was over its size cap.
import type { RunRecord } from "@/lib/api/sync";

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

/** Whether a round changed anything ON THIS MACHINE — which is the only
 *  thing an undo can reverse. A round that merely published pushed local
 *  state up; reversing its snapshot restores a local tree that never moved. */
function appliedSomething(run: RunRecord): boolean {
  const { added, modified, deleted } = run.applied;
  return added + modified + deleted > 0;
}

/**
 * The id of the one round `POST /sync/rollback` would undo, or null.
 *
 * The route takes no argument: it reverses the NEWEST pre-apply snapshot. So
 * the surface has to work out which row that is rather than offering the same
 * call from every row under a different name.
 *
 * And then it has to ask whether that round left anything to reverse, which
 * is the part that was missing. Every round reaching the apply step tags a
 * snapshot — including one that applies nothing — so after a single quiet
 * round the newest snapshot is the vault exactly as it already is. "Undo this
 * round" on a row reading `+0 ~0 −0` offers to restore the state it is
 * already in: a button that does nothing, on the row that says nothing
 * happened.
 *
 * It also cannot be moved down to the last round that DID apply something.
 * The quiet round's snapshot is now the newest one, so the daemon would
 * reverse to that and leave the older round standing — the button would name
 * one round and undo another. No button is the honest answer, and
 * `coffer sync restore` is what reaches further back.
 *
 * `failed` deliberately ends the walk with no target for the same reason: a
 * failed round may have died before the snapshot or after it, and the status
 * cannot say which.
 *
 * Lives here beside `heldRoundId` because the two answer one question —
 * WHICH row may act — for two routes that share the same shape: neither names
 * a round, so the surface has to name it for them.
 *
 * @param runs the history, newest first, exactly as the daemon returns it.
 */
export function rollbackTargetId(runs: RunRecord[]): number | null {
  for (const run of runs) {
    if (SNAPSHOTTED.has(run.status)) return appliedSomething(run) ? run.id : null;
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
