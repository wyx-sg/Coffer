// frontend/src/lib/hooks/useSync.ts
//
// Every query and mutation for the Sync page's remote / round / master-key
// half (spec vault-sync). The machine registry lives in `useMachines.ts`,
// because it is the other tab and has its own invalidation story.
//
// Two queries on purpose: `GET /sync/remote` is the configuration the form
// edits, and `GET /sync/status` carries the last round plus this machine's id,
// which the form never writes. Anything that can change the round — running
// one, confirming or rejecting a held one, rolling one back — invalidates the
// status, the registry (a round republishes descriptors), and the resource
// caches a round can have rewritten underneath the page.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { syncApi, type ConvergeRound, type SyncRemoteInput } from "@/lib/api/sync";
import { useToast } from "@/components/ui/toast";
import {
  agentsKey,
  knowledgeKey,
  resourcesKey,
  skillsKey,
  syncKey,
  syncKeyFingerprintKey,
  syncRemoteKey,
  syncRunsKey,
  syncStatusKey,
} from "@/lib/api/queryKeys";

export function useSyncRemote() {
  return useQuery({ queryKey: syncRemoteKey, queryFn: () => syncApi.getRemote() });
}

export function useSyncStatus() {
  return useQuery({ queryKey: syncStatusKey, queryFn: () => syncApi.status() });
}

/**
 * Every round this vault has run, newest first — the History tab.
 *
 * `enabled` is false while another tab is in front: Radix unmounts the others,
 * and the query is gated besides, so nothing is fetched and thrown away. The
 * key is under `syncKey`, so running, confirming, rejecting or rolling back a
 * round refreshes the history along with the status.
 */
export function useSyncRuns(enabled = true) {
  return useQuery({ queryKey: syncRunsKey, queryFn: () => syncApi.runs(), enabled });
}

/**
 * Invalidate everything a converge round can have moved. A round applies the
 * remote's diff straight into the vault — resources, skills, agents, knowledge
 * — so the page's own caches are not the only stale ones afterwards.
 */
function useRoundInvalidation() {
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
 * Store the remote, replacing any previous one — behind the card's Save
 * button, or from the "converge automatically" switch flipping the stored
 * remote. `worktree_path` rides along unchanged when the daemon already has
 * one: the card does not offer it, and omitting it would silently reset an
 * adopted working tree to the default.
 */
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

/**
 * Run one converge round now. Held and conflicted rounds come back as a 200
 * carrying the story, not as an error, so the page renders them as banners —
 * and every completed round toasts its outcome, so a click on "Converge now"
 * is never answered by silence. The counts sum both directions: what the
 * round applied here plus what it published, which is what the round moved.
 */
export function useRunConverge() {
  const invalidate = useRoundInvalidation();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: () => syncApi.run(),
    onSuccess: (round: ConvergeRound) => {
      invalidate();
      const applied = round.applied ?? { added: 0, modified: 0, deleted: 0 };
      const published = round.published ?? { added: 0, modified: 0, deleted: 0 };
      toast.success(
        t("sync.toast.roundDone", {
          status: t(`sync.round.statusLabel.${round.status}`, { defaultValue: round.status }),
          added: applied.added + published.added,
          modified: applied.modified + published.modified,
          deleted: applied.deleted + published.deleted,
        }),
      );
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** Accept a round the deletion guard held, and let it finish. */
export function useConfirmRound() {
  const invalidate = useRoundInvalidation();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: () => syncApi.confirm(),
    onSuccess: invalidate,
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** Discard a held round. Nothing is applied and nothing is published. */
export function useRejectRound() {
  const invalidate = useRoundInvalidation();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: () => syncApi.reject(),
    onSuccess: invalidate,
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** Rebuild this machine from the remote, discarding local-only documents.
 *  Destructive on purpose: only offered where a publish-side hold means this
 *  machine is the damaged one, and only ever on an explicit click. */
export function useRebuildFromRemote() {
  const invalidate = useRoundInvalidation();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: () => syncApi.rebuild(),
    onSuccess: invalidate,
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** The key's short hash — never the key. Null when this vault holds none. */
export function useKeyFingerprint() {
  return useQuery({
    queryKey: syncKeyFingerprintKey,
    queryFn: () => syncApi.keyFingerprint(),
  });
}

/**
 * Hand this machine's key back to the page so it can be downloaded as a file.
 * The material crosses only the loopback origin the user is already
 * authenticated against; it is never written into the repository.
 */
export function useExportMasterKey() {
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: () => syncApi.exportKey(),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/**
 * Install a key the user carried here as a FILE, read in the browser. The
 * daemon never resolves a path the page named, and the browser never has to
 * learn one. Refreshes the fingerprint and the round, whose `locked_refs` this
 * is the answer to.
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
