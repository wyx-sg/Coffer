// frontend/src/pages/sync/useSyncIgnore.ts — Ignore for the Sync page's banners (principle 19).
//
// A banner's × is the same Ignore as on Overview: the daemon keeps it under
// the attention item's key (`sync:<fingerprint>:<reason_code>`), so the
// menu bar and this page agree, and the banner returns by
// itself when the situation changes (the fingerprint changes with it). The
// page header says "ignored on Overview" while one is ignored.
import { useAttention } from "@/lib/hooks/useAttention";
import { useIgnoreAttention } from "@/lib/hooks/useAttentionIgnore";
import type { SyncProblem } from "@/lib/api/sync";

/** The attention reason each kind of sync problem is reported under. */
export const PROBLEM_REASON: Partial<Record<SyncProblem["kind"], string>> = {
  push_failed: "sync_push_failed",
  plaintext_found: "sync_plaintext_found",
  unreachable: "sync_unreachable",
  auth_failed: "sync_auth_failed",
  waiting_approval: "sync_waiting_approval",
  cloud_folder: "sync_paused",
  git_missing: "sync_git_missing",
  layout: "sync_layout",
};

export const STOP_REASON = { conflicts: "sync_conflicts", held: "sync_deletions_held" } as const;

export function useSyncIgnore() {
  const attention = useAttention();
  const ignore = useIgnoreAttention();
  const items = attention.data?.items ?? [];
  const ignored = attention.data?.ignored ?? [];
  return {
    /** Whether the situation behind `reason` is ignored right now. */
    isIgnored: (reason: string) =>
      ignored.some((i) => i.kind === "sync" && i.reason_code === reason),
    /** The × handler for `reason`, or undefined while the daemon lists no such item. */
    ignorer: (reason: string): (() => void) | undefined => {
      const key = items.find((i) => i.kind === "sync" && i.reason_code === reason)?.key;
      return key ? () => ignore.mutate(key) : undefined;
    },
  };
}
