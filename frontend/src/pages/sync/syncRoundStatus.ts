// frontend/src/pages/sync/syncRoundStatus.ts
//
// A round's status as a word and a tone — one mapping for the Runs table, the
// round detail and the Machines tab's "last round" column, so the three never
// call one outcome two things.
import type { TFunction } from "i18next";

import type { RoundStatus, SyncChange } from "@/lib/api/sync";
import type { Tone } from "@/lib/statusColors";

/**
 * `nothing_to_do` is `muted` rather than `ok` on purpose: it succeeded, but a
 * wall of green for rounds that did nothing would drown the ones that did.
 * `push_failed` is a warning and not an error — everything landed here and
 * the commit is waiting, which is a different situation from a round that
 * could not run at all.
 */
const STATUS_TONE: Record<RoundStatus, Tone> = {
  nothing_to_do: "muted",
  pulled: "ok",
  pushed: "ok",
  pulled_and_pushed: "ok",
  joined: "ok",
  rolled_back: "ok",
  push_failed: "warn",
  stopped: "warn",
  held: "warn",
  waiting_on_edit: "warn",
  join_required: "warn",
  paused_cloud_folder: "warn",
  unreachable: "error",
  auth_failed: "error",
  remote_too_new: "error",
  remote_too_old: "error",
  failed: "error",
};

/** Every status, in the order the Runs filter offers them. */
export const ROUND_STATUSES = Object.keys(STATUS_TONE) as RoundStatus[];

export function statusTone(status: string): Tone {
  return STATUS_TONE[status as RoundStatus] ?? "muted";
}

/** A round's status as a word, falling back to the wire value verbatim. */
export function statusLabel(t: TFunction, status: string): string {
  return t(`sync.round.status.${status}`, { defaultValue: status });
}

/** `+ path`, `~ path`, `− path` — one mark per change kind, the same in a
 *  round's detail and in the rollback dialog. */
export function changeLine(change: SyncChange): string {
  const mark = change.status === "added" ? "+" : change.status === "removed" ? "−" : "~";
  return `${mark} ${change.path}`;
}
