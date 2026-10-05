// frontend/src/lib/hooks/useSync.ts
//
// The Sync page's status, rounds, remote, and rollback queries and
// mutations (spec vault-sync). What a stopped round asks of a person — the
// conflict answers, the held deletions, the join — lives in `useSyncStop.ts`;
// the machine registry in `useMachines.ts`.
//
// One query carries most of the page: `GET /sync/status` holds the remote, the
// last round, what is waiting to push and what is wrong, so the cards read out
// of the status they already have rather than fetching pieces twice. Anything
// that can move a round invalidates the status, the registry, and the resource
// caches a round can have rewritten underneath the page.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import {
  syncApi,
  type RemoteCheckInput,
  type SyncRemoteInput,
  type SyncRound,
} from "@/lib/api/sync";
import { useToast } from "@/components/ui/toast";
import { FIRST_PAGE, MORE_PAGE, useInfiniteList } from "@/lib/hooks/useInfiniteList";
import { invalidateSync } from "@/lib/syncInvalidate";
import { roundToast } from "@/lib/syncRoundToast";
import {
  agentsKey,
  knowledgeKey,
  resourcesKey,
  skillsKey,
  syncKey,
  syncRunsKey,
  syncStatusKey,
} from "@/lib/api/queryKeys";

/**
 * The status. Polled, because a round that needs a person can start needing
 * one while the user sits on the page. Slowly: rounds run on the order of minutes, so a minute's lag
 * costs nothing and a background tab wakes the daemon for nothing.
 */
export function useSyncStatus(enabled = true) {
  return useQuery({
    queryKey: syncStatusKey,
    queryFn: () => syncApi.status(),
    enabled,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });
}

/**
 * The rounds, newest first: 30, then 50 more as the reader reaches the end of
 * the table. A refresh after a round re-reads the first page only
 * (`invalidateSync`). `enabled` is false while another tab is in front.
 */
export function useSyncRuns(enabled = true) {
  return useInfiniteList<SyncRound>({
    queryKey: syncRunsKey,
    enabled,
    fetchPage: async (cursor, signal) => {
      const page = await syncApi.runs({ cursor, limit: cursor ? MORE_PAGE : FIRST_PAGE }, signal);
      return { items: page.rounds, next: page.next_cursor ?? null, total: page.total };
    },
  });
}

/**
 * Invalidate everything a round can have moved. A round checks the merged
 * tree out into the vault — resources, skills, agents, knowledge — so the
 * page's own caches are not the only stale ones afterwards.
 */
function useRoundInvalidation() {
  const qc = useQueryClient();
  return () => {
    invalidateSync(qc);
    void qc.invalidateQueries({ queryKey: resourcesKey });
    void qc.invalidateQueries({ queryKey: skillsKey });
    void qc.invalidateQueries({ queryKey: agentsKey });
    void qc.invalidateQueries({ queryKey: knowledgeKey });
  };
}

/**
 * A mutation that ends in a round: invalidates what the round moved and
 * toasts its outcome, so a click is never answered by silence. Stopped, held
 * and join-required rounds come back as a 200 carrying their story, so the
 * toast reads the round's status, not the HTTP status.
 *
 * `toastErrors: false` for calls made from a ConfirmDialog, which renders the
 * failure in place and stays open — a toast as well would report it twice.
 */
export function useRoundMutation<A>(
  fn: (arg: A) => Promise<SyncRound>,
  { toastErrors = true }: { toastErrors?: boolean } = {},
) {
  const invalidate = useRoundInvalidation();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: fn,
    onSuccess: (round: SyncRound) => {
      invalidate();
      const { variant, message } = roundToast(t, round);
      toast[variant](message);
    },
    onError: toastErrors ? (error) => toast.error(translateApiError(t, error)) : undefined,
  });
}

/** "Sync now": run one round. */
export function useRunSync() {
  return useRoundMutation<void>(() => syncApi.run());
}

/** "Push anyway": push what the last round refused as a plaintext secret. */
export function usePushAnyway() {
  return useRoundMutation<void>(() => syncApi.pushAnyway());
}

/** Store the remote, replacing any previous one. Pause and resume are this
 *  same call with `enabled` flipped. */
export function useSaveSyncRemote() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (remote: SyncRemoteInput) => syncApi.putRemote(remote),
    meta: { secretDestination: () => "remote" },
    onSuccess: () => invalidateSync(qc),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** "Move vault": relocate the vault out of a synchronised folder. Reached only from its
 *  dialog, which renders a failure in place. */
export function useMoveVault() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (to: string) => syncApi.moveVault(to),
    onSuccess: () => invalidateSync(qc),
  });
}

/** "Stop syncing": forget the remote. It runs at once; the caller's toast offers Undo
 *  (`useRestoreSyncRemote`) when the answer says it is `restorable`. */
export function useClearSyncRemote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => syncApi.clearRemote(),
    onSuccess: () => invalidateSync(qc),
  });
}

/** Undo "Stop syncing": the forgotten remote comes back as it was. A refusal
 *  (nothing to restore, or a remote set up since) is a toast. */
export function useRestoreSyncRemote() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: () => syncApi.restoreRemote(),
    meta: { secretDestination: () => "remote" },
    onSuccess: () => invalidateSync(qc),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** Ask what a repository holds before it becomes the remote. The answer is
 *  rendered in place, failures included, so there is no error toast. */
export function useCheckRemote() {
  return useMutation({ mutationFn: (body: RemoteCheckInput) => syncApi.checkRemote(body) });
}

/** What rolling round `runId` back would do — fetched only while its dialog is open. */
export function useRollbackPlan(runId: number | null, enabled: boolean) {
  return useQuery({
    queryKey: [...syncKey, "rollback-plan", runId],
    queryFn: () => syncApi.rollbackPlan(runId as number),
    enabled: enabled && runId !== null,
  });
}

/** Roll a round back, as a new commit the next round pushes. From a dialog. */
export function useRollbackRound() {
  return useRoundMutation<number>((runId) => syncApi.rollback(runId), { toastErrors: false });
}

/** A plaintext finding in its file, fetched when its place is opened. The
 * answer follows the last round, so it is refetched with the status. */
export function usePlaintextContext(path: string, line: number, enabled: boolean) {
  return useQuery({
    queryKey: [...syncKey, "plaintext", path, line],
    queryFn: () => syncApi.plaintextContext(path, line),
    enabled,
    retry: false,
  });
}

/** A round's file as a diff, fetched when its row is opened. A round's commits
 * never change, so the answer is kept. */
export function useRoundFileDiff(
  runId: number,
  path: string,
  side: "applied" | "pushed",
  enabled: boolean,
) {
  return useQuery({
    queryKey: [...syncRunsKey, runId, "diff", side, path],
    queryFn: () => syncApi.runDiff(runId, path, side),
    enabled,
    staleTime: Infinity,
    retry: false,
  });
}
