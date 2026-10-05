// src/lib/inlineApproval.ts — a change saved in the desktop app approves the secret binding it waits on, on the spot.
//
// A save that sends a stored secret somewhere new leaves an approval waiting
// (spec secret "Hold a secret for a new destination until a person approves it"). The daemon
// cannot tell the person's click from an agent's call with the same token, so
// the approval still needs the shell's presence check — but when the person
// saved it in the desktop app, that check runs as part of the save: one
// Touch ID right after Save, for exactly the approvals that save created on
// that resource, and no separate approvals sheet. A browser has no presence
// check, so there the approval waits as before.
//
// A mutation opts in with `meta: { secretDestination: (data, variables) => uid }`,
// the uid of the destination its save may bind (a resource uid, or "remote"
// for the sync remote); the query client's mutation cache runs the rest. A
// save made without a mutation wraps itself in `withInlineApproval`.
//
// While such a save runs, the approvals sheet does not open on its own, so it
// never races the presence prompt; a prompt the person cancels leaves the
// approval waiting, shown on the resource, without popping the sheet.
import { MutationCache, type Mutation } from "@tanstack/react-query";

import { secretsApi } from "@/lib/api/secret";
import { approvePending, approvePendingBatch, presenceAvailable } from "@/lib/tauri";

/** What a mutation's `meta` carries to opt in. */
export type SecretDestinationOf = (data: unknown, variables: unknown) => string | null | undefined;

/** The window event that tells the approvals sheet to leave these ids closed. */
export const DECLINED_APPROVALS_EVENT = "coffer:approvals-declined";

// --- the hold: while a save approves inline, the sheet stays shut ----------
let holds = 0;
const listeners = new Set<() => void>();

function setHolds(next: number): void {
  holds = next;
  listeners.forEach((l) => l());
}

/** Whether a save is approving inline right now. */
export function approvalsHeld(): boolean {
  return holds > 0;
}

/** Subscribe to the hold (for `useSyncExternalStore`). */
export function subscribeApprovalsHeld(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

// --- the approval itself ---------------------------------------------------

/** How long before the save started an approval may be stamped and still count as its own. */
const CLOCK_SLACK_MS = 2_000;

/**
 * Approve, under one presence check, what a save just left waiting on
 * `destinationUid`. Only bindings created since `since` count, so nothing an
 * agent asked for earlier is swept into the person's confirmation. Never
 * throws: the save already happened, and what is not approved stays waiting.
 */
export async function approveWhatTheSaveAwaits(
  destinationUid: string | readonly string[],
  since: number,
): Promise<"none" | "approved" | "declined"> {
  const destinations = new Set(
    typeof destinationUid === "string" ? [destinationUid] : destinationUid,
  );
  let ids: string[];
  try {
    const { approvals } = await secretsApi.pendingApprovals();
    ids = approvals
      .filter(
        (a) =>
          a.op === "bind" &&
          a.destination_uid !== null &&
          destinations.has(a.destination_uid) &&
          Date.parse(a.created_at) >= since - CLOCK_SLACK_MS,
      )
      .map((a) => a.id);
  } catch {
    return "none";
  }
  if (ids.length === 0) return "none";
  try {
    if (ids.length === 1) await approvePending(ids[0]);
    else await approvePendingBatch(ids);
    return "approved";
  } catch {
    // Cancelled, or the check failed: it stays waiting, shown where it was saved.
    window.dispatchEvent(new CustomEvent(DECLINED_APPROVALS_EVENT, { detail: ids }));
    return "declined";
  }
}

/** Run a save that is not a mutation, approving inline what it leaves waiting —
 *  on one destination, or on several under one presence check (a batch import). */
export async function withInlineApproval<T>(
  save: () => Promise<T>,
  destinationOf: (result: T) => string | readonly string[] | null | undefined,
): Promise<T> {
  if (!presenceAvailable()) return save();
  const since = Date.now();
  setHolds(holds + 1);
  try {
    const result = await save();
    const uid = destinationOf(result);
    if (uid && uid.length > 0) await approveWhatTheSaveAwaits(uid, since);
    return result;
  } finally {
    setHolds(holds - 1);
  }
}

// --- the mutation cache that runs it for opted-in mutations ---------------

const started = new WeakMap<Mutation<unknown, unknown, unknown, unknown>, number>();

function destinationOf(mutation: Mutation<unknown, unknown, unknown, unknown>) {
  const of = mutation.options.meta?.secretDestination;
  return typeof of === "function" ? (of as SecretDestinationOf) : null;
}

/** The query client's mutation cache: approves inline for mutations that opt in. */
export function inlineApprovalMutationCache(): MutationCache {
  return new MutationCache({
    onMutate: (_variables, mutation) => {
      if (!destinationOf(mutation) || !presenceAvailable()) return;
      started.set(mutation, Date.now());
      setHolds(holds + 1);
    },
    onSuccess: async (data, variables, _context, mutation) => {
      const since = started.get(mutation);
      const of = destinationOf(mutation);
      if (since === undefined || !of) return;
      const uid = of(data, variables);
      if (uid) await approveWhatTheSaveAwaits(uid, since);
    },
    onSettled: (_data, _error, _variables, _context, mutation) => {
      if (!started.has(mutation)) return;
      started.delete(mutation);
      setHolds(holds - 1);
    },
  });
}
