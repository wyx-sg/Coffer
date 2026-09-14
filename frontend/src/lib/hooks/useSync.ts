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
import { syncApi, type SyncRemoteInput } from "@/lib/api/sync";
import { useToast } from "@/components/ui/toast";

export const syncKey = ["sync"] as const;
export const syncRemoteKey = ["sync", "remote"] as const;
export const syncStatusKey = ["sync", "status"] as const;
export const syncMachinesKey = ["sync", "machines"] as const;
export const syncKeyFingerprintKey = ["sync", "key-fingerprint"] as const;

export function useSyncRemote() {
  return useQuery({ queryKey: syncRemoteKey, queryFn: () => syncApi.getRemote() });
}

export function useSyncStatus() {
  return useQuery({ queryKey: syncStatusKey, queryFn: () => syncApi.status() });
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
    void qc.invalidateQueries({ queryKey: ["resources"] });
    void qc.invalidateQueries({ queryKey: ["skills"] });
    void qc.invalidateQueries({ queryKey: ["agents"] });
    void qc.invalidateQueries({ queryKey: ["knowledge"] });
  };
}

/**
 * Store the remote, replacing any previous one — the card auto-saves, so this
 * fires whenever the user finishes with a field rather than behind a Save
 * button. `worktree_path` rides along unchanged when the daemon already has
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

/** Run one converge round now. Held and conflicted rounds come back as a 200
 *  carrying the story, not as an error, so the page renders them as banners. */
export function useRunConverge() {
  const invalidate = useRoundInvalidation();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: () => syncApi.run(),
    onSuccess: invalidate,
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
