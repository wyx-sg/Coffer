// frontend/src/pages/sync/syncPageState.ts
//
// "Is this Mac in sync?" in one answer. The Sync page's header pill, its
// primary button and the banner on the Status tab all read the same state, so
// they can never disagree about what is going on.
//
// The order is the order a person needs it in: a round running now says more
// than the last one did; a paused remote asks for nothing (spec vault-sync
// "Pause a configured remote without forgetting it"), so it outranks what it
// would otherwise raise; a stopped round outranks a failed push, because
// nothing moves until it is answered; and what waits to push outranks what
// the last round pulled, because it is what the next round does.
import type { SyncStatus } from "@/lib/api/sync";
import type { StatusTone } from "@/lib/statusTone";

export type SyncStateKind =
  | "setup"
  | "syncing"
  | "paused"
  | "conflicts"
  | "held"
  | "push_failed"
  | "plaintext_found"
  | "unreachable"
  | "auth_failed"
  | "waiting_approval"
  | "cloud_folder"
  | "git_missing"
  | "layout"
  | "failed"
  | "to_push"
  | "pulled"
  | "in_sync";

/** The pill's colour: the four status tones, plus `info` for "something is moving". */
export type PillTone = StatusTone | "info";

export interface SyncState {
  kind: SyncStateKind;
  /** The count a pill carries ("2 changes to push", "Stopped: 2 conflicts"). */
  count: number;
  tone: PillTone;
}

const PILL_TONE: Record<SyncStateKind, PillTone> = {
  setup: "off",
  syncing: "info",
  paused: "off",
  conflicts: "err",
  held: "err",
  push_failed: "err",
  plaintext_found: "err",
  unreachable: "warn",
  auth_failed: "err",
  waiting_approval: "warn",
  cloud_folder: "warn",
  git_missing: "err",
  layout: "err",
  failed: "err",
  to_push: "info",
  pulled: "ok",
  in_sync: "ok",
};

/** Every file the next round pushes — a commit can carry several. */
export function waitingCount(status: SyncStatus): number {
  return status.waiting.reduce((n, commit) => n + commit.changes.length, 0);
}

/** Whether this Mac is set up to sync at all: a remote, and joined to it. */
function isSetUp(status: SyncStatus): boolean {
  return status.configured && status.joined && status.remote !== null;
}

function kindOf(status: SyncStatus, pending: boolean): SyncStateKind {
  if (!isSetUp(status)) return "setup";
  if (pending || status.running_since !== null) return "syncing";
  if (status.remote && !status.remote.enabled) return "paused";
  if (status.conflicts > 0) return "conflicts";
  if (status.held > 0) return "held";
  const problem = status.problem?.kind;
  if (problem === "cloud_folder") return "cloud_folder";
  if (problem) return problem;
  if (waitingCount(status) > 0) return "to_push";
  if (status.last_round?.status === "pulled") return "pulled";
  return "in_sync";
}

/** The page's state; `pending` is a round this page asked for and is still waiting on. */
export function syncState(status: SyncStatus, pending = false): SyncState {
  const kind = kindOf(status, pending);
  const count =
    kind === "conflicts"
      ? status.conflicts
      : kind === "held"
        ? status.held
        : kind === "to_push"
          ? waitingCount(status)
          : kind === "pulled"
            ? (status.last_round?.pulled_files ?? 0)
            : 0;
  return { kind, count, tone: PILL_TONE[kind] };
}

/** The header's primary button for a state. */
export function primaryAction(kind: SyncStateKind): {
  label: "syncNow" | "syncing" | "tryAgain";
  disabled: boolean;
} {
  if (kind === "syncing") return { label: "syncing", disabled: true };
  if (kind === "unreachable" || kind === "auth_failed" || kind === "waiting_approval")
    return { label: "tryAgain", disabled: false };
  // A stopped round is answered on its own page; another round would only stop again.
  return { label: "syncNow", disabled: kind === "conflicts" || kind === "held" };
}
