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
import { useMatch } from "react-router-dom";

import type { ConvergeRound, RoundStatus, SyncStatus } from "@/lib/api/sync";
import { useSyncStatus } from "@/lib/hooks/useSync";
import { useFeatureEnabled } from "@/lib/hooks/useFeatures";

const SEEN_KEY = "coffer.sync.attentionSeen";

/**
 * The round statuses that mean the user has something to do — the same set the
 * CLI exits non-zero on (`_NEEDS_ATTENTION` in `surfaces/cli/sync_cmd.py`).
 * Kept as one list rather than four call sites so a status added there is
 * added here too, and not silently carried by one surface only.
 */
const NEEDS_ATTENTION: readonly RoundStatus[] = [
  "conflict",
  "awaiting_confirmation",
  "push_failed",
  "failed",
  "awaiting_join",
];

/**
 * What this situation is, for the purpose of "have I seen it?", or `null`
 * when there is nothing to see.
 *
 * The SITUATION, not the round. A timer re-raises the same broken thing every
 * hour, and a marker keyed on the round — its time, its id — would call each
 * repeat news and put the dot back every hour over a problem the user has
 * already read. Keyed on what is actually wrong, a repeat is the same marker
 * and stays quiet, while a *different* failure, a hold raised in the other
 * direction, or one whose breaches have changed mints a new one and asks
 * again. That is the difference between telling someone something and
 * nagging them.
 *
 * Cheap to compute and small to store: the fields a reader would use to say
 * "same problem", never the whole payload — `pending.paths` alone can be
 * hundreds of entries.
 */
export function attentionMarker(round: ConvergeRound | null | undefined): string | null {
  if (!round || !NEEDS_ATTENTION.includes(round.status)) return null;
  const breaches = (round.pending?.breaches ?? [])
    .map((b) => `${b.area}:${b.deleted}/${b.total}`)
    .join(",");
  return [
    round.status,
    round.error ?? "",
    round.conflicts.join(","),
    round.pending?.direction ?? "",
    breaches,
  ].join("|");
}

/**
 * The marker for a whole `GET /sync/status` body: `attentionMarker` of its last
 * round, but only while the remote is switched ON. A paused remote makes a round
 * return `disabled` WITHOUT recording it, so `last_run` keeps whatever it last
 * was; the CLI (`coffer sync status`) and the desktop shell both stay quiet
 * then, and so does the dot (spec vault-sync "Pause a configured remote without
 * forgetting it").
 */
export function syncStatusMarker(status: SyncStatus | null | undefined): string | null {
  if (status?.remote?.enabled !== true) return null;
  return attentionMarker(status.last_run);
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
  const onSyncPage = useMatch("/sync") !== null;
  // Switching `vault_sync` off stops every sync attention mark (spec
  // experimental-features "Withdraw what a switched-off feature put in front
  // of agents") — and asks nothing, so a switched-off feature is not polled.
  const syncOn = useFeatureEnabled("vault_sync") === true;
  const { data, isError } = useSyncStatus(syncOn);
  const marker = syncStatusMarker(data);

  useEffect(() => {
    if (onSyncPage && marker) writeSeen(marker);
  }, [onSyncPage, marker]);

  // A daemon that cannot answer is not a sync problem, and the offline banner
  // already says so; stale cached data must not outlive it into a second
  // claim on the same screen.
  if (!syncOn || isError || !marker) return false;
  // While the page is open the user is looking at it — no dot over their own
  // reading, and no flicker between the render and the effect above.
  if (onSyncPage) return false;
  return marker !== readSeen();
}
