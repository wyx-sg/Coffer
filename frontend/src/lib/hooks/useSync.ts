// frontend/src/lib/hooks/useSync.ts
//
// The Sync page's status, rounds, remote, rollback and master-key queries and
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
import { roundToast } from "@/lib/syncRoundToast";
import {
  agentsKey,
  knowledgeKey,
  resourcesKey,
  skillsKey,
  syncKey,
  syncKeyFingerprintKey,
  syncRunsKey,
  syncStatusKey,
} from "@/lib/api/queryKeys";

/**
 * The status. Polled, because the sidebar dot mounts this on every page and a
 * round that needs a person can start needing one while the user sits on some
 * other page. Slowly: rounds run on the order of minutes, so a minute's lag
 * costs nothing and a background tab wakes the daemon for nothing.
 */
export function useSyncStatus() {
  return useQuery({
    queryKey: syncStatusKey,
    queryFn: () => syncApi.status(),
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });
}

/** Every round, newest first. `enabled` is false while another tab is in front. */
export function useSyncRuns(enabled = true) {
  return useQuery({ queryKey: syncRunsKey, queryFn: () => syncApi.runs(), enabled });
}

/**
 * Invalidate everything a round can have moved. A round checks the merged
 * tree out into the vault — resources, skills, agents, knowledge — so the
 * page's own caches are not the only stale ones afterwards.
 */
export function useRoundInvalidation() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: syncKey });
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

/** Store the remote, replacing any previous one. Pause and resume are this
 *  same call with `enabled` flipped. */
export function useSaveSyncRemote() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (remote: SyncRemoteInput) => syncApi.putRemote(remote),
    onSuccess: () => void qc.invalidateQueries({ queryKey: syncKey }),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** "Stop syncing": forget the remote. Reached only from a ConfirmDialog. */
export function useClearSyncRemote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => syncApi.clearRemote(),
    onSuccess: () => void qc.invalidateQueries({ queryKey: syncKey }),
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

/** The key's short hash — never the key. Null when this vault holds none. */
export function useKeyFingerprint() {
  return useQuery({
    queryKey: syncKeyFingerprintKey,
    queryFn: () => syncApi.keyFingerprint(),
  });
}

/**
 * Install a key the user carried here as a FILE, read in the browser. The
 * daemon never resolves a path the page named, and the browser never has to
 * learn one.
 */
export function useImportMasterKey() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (material: string) => syncApi.importKey(material),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: syncKey });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
