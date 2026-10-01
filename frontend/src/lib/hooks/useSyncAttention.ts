// frontend/src/lib/hooks/useSyncAttention.ts
//
// Whether the sidebar's Sync entry should be carrying a dot.
//
// This replaces a floating banner that sat over whatever page the user was on
// (spec vault-sync "Say a vault needs a human where the user already is"). The banner was right
// about the problem — a held or failed vault stops converging AND stops backing up, and the only
// surface that says so is the page nobody opens — and wrong about the remedy. It
// covered the page, it said nothing the destination did not say better, and
// it came back on every render of every page until the situation was answered,
// which for a stretch of hourly failures is a banner that never leaves.
//
// A dot on the entry says the same thing in the place the user already looks
// to navigate, and it is *seen* by going there. That is the whole difference:
// a notification the user can acknowledge by acting on it, rather than one
// that argues until the underlying state changes.
//
// "Seen" is per browser and deliberately not synced: it is a fact about this
// person's attention, not about the vault.
import { useEffect } from "react";

import type { RoundStatus, SyncRound, SyncStatus } from "@/lib/api/sync";
import { useSyncStatus } from "@/lib/hooks/useSync";
import { usePageLocation } from "@/lib/settingsModal";

const SEEN_KEY = "coffer.sync.attentionSeen";

/**
 * The round statuses that leave the vault needing a person — the backend's
 * `NEEDS_PERSON` (`domain/sync/rounds.py`) plus the two failures that stop
 * every other machine from seeing this one's work. Kept as one list so a
 * status added there is added here too.
 */
const NEEDS_ATTENTION: readonly RoundStatus[] = [
  "stopped",
  "held",
  "waiting_on_edit",
  "join_required",
  "auth_failed",
  "paused_cloud_folder",
  "remote_too_new",
  "remote_too_old",
  "push_failed",
  "plaintext_found",
  "unreachable",
  "failed",
];

/**
 * What a round's situation is, for the purpose of "have I seen it?", or
 * `null` when there is nothing to see.
 *
 * The SITUATION, not the round. A timer re-raises the same broken thing every
 * few minutes, and a marker keyed on the round — its time, its id — would call
 * each repeat news and put the dot back over a problem the user has already
 * read. Keyed on what is wrong, a repeat is the same marker and stays quiet,
 * while a different failure, or a stop with a different number of files,
 * mints a new one and asks again.
 *
 * Small on purpose: this goes into localStorage, so it carries the counts a
 * reader would use to say "same problem", never the paths.
 */
export function attentionMarker(round: SyncRound | null | undefined): string | null {
  if (!round || !NEEDS_ATTENTION.includes(round.status)) return null;
  return [round.status, round.detail ?? "", round.conflicts, round.held].join("|");
}

/**
 * The marker for a whole `GET /sync/status` body, only while the remote is
 * switched ON: a paused remote runs no round, so whatever it last said is not
 * a question any more (spec vault-sync "Pause a configured remote without
 * forgetting it").
 *
 * The status says more than its last round: a machine that has not joined, a
 * stopped round and a join with unanswered files all ask for a person whatever
 * the newest round's outcome was.
 */
export function syncStatusMarker(status: SyncStatus | null | undefined): string | null {
  if (status?.remote?.enabled !== true) return null;
  const parts: string[] = [];
  if (!status.joined) parts.push("join_required");
  if (status.conflicts > 0) parts.push(`conflicts:${status.conflicts}`);
  if (status.held > 0) parts.push(`held:${status.held}`);
  if (status.join_choices > 0) parts.push(`join_choices:${status.join_choices}`);
  if (status.problem) parts.push(`${status.problem.kind}:${status.problem.message}`);
  const round = attentionMarker(status.last_round);
  if (round) parts.push(round);
  return parts.length > 0 ? parts.join("|") : null;
}

function readSeen(): string | null {
  try {
    return localStorage.getItem(SEEN_KEY);
  } catch {
    // Private windows and blocked site data both throw. A dot that shows one
    // time too many is a far better failure than a page that will not render.
    return null;
  }
}

function writeSeen(marker: string): void {
  try {
    localStorage.setItem(SEEN_KEY, marker);
  } catch {
    /* see readSeen */
  }
}

/**
 * True while the vault needs an answer the user has not looked at yet.
 *
 * Marks the current situation seen for as long as the Sync page is open, not
 * once on arrival: a user who leaves the page open through the next hourly
 * round has plainly seen that one too, and a dot appearing under their eyes
 * on the very page that explains it would be noise.
 */
export function useSyncAttention(): boolean {
  // The page the user is on — the one under the Settings modal while it is
  // open, so opening Settings over Sync does not raise the dot.
  const onSyncPage = usePageLocation().pathname === "/sync";
  const { data, isError } = useSyncStatus();
  const marker = syncStatusMarker(data);

  useEffect(() => {
    if (onSyncPage && marker) writeSeen(marker);
  }, [onSyncPage, marker]);

  // A daemon that cannot answer is not a sync problem, and the offline banner
  // already says so; stale cached data must not outlive it into a second
  // claim on the same screen.
  if (isError || !marker) return false;
  // While the page is open the user is looking at it — no dot over their own
  // reading, and no flicker between the render and the effect above.
  if (onSyncPage) return false;
  return marker !== readSeen();
}
