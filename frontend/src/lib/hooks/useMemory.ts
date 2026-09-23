// frontend/src/lib/hooks/useMemory.ts
//
// ALL queries + mutations for the `memory` kind (agents/frontend.md §3). Keys
// are hierarchical under one `["memory"]` root so a write with cross-cutting
// effects — a sync, a distil pass — can invalidate the whole subtree with a
// prefix, mirroring `lib/hooks/useKnowledge.ts`.
//
// A partition's file keys hang off that partition's own key rather than a
// sibling root, because a sync or distil pass rewrites the files on disk:
// nesting them means the broad invalidation those mutations already do
// reaches the open preview too, with no key threaded through by hand.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { ApiError, translateApiError } from "@/lib/api/errors";
import {
  distil,
  installDelivery,
  listDelivery,
  listPartitionFiles,
  listPartitions,
  readPartitionFile,
  removeDelivery,
  sync,
} from "@/lib/api/memory";
import {
  memoryAgentDeliveryKey,
  memoryDeliveryKey,
  memoryKey,
  memoryPartitionFileKey,
  memoryPartitionFilesKey,
  memoryPartitionsKey,
  upkeepRunsKey,
} from "@/lib/api/queryKeys";

/** Aggregation and the distil pass both rewrite whole partitions on disk —
 * partition list, note counts and every file under them — so both invalidate
 * the full `["memory"]` prefix rather than threading a narrower key. */
function invalidateMemory(qc: ReturnType<typeof useQueryClient>): void {
  void qc.invalidateQueries({ queryKey: memoryKey });
}

export function useMemoryPartitions() {
  return useQuery({
    queryKey: memoryPartitionsKey,
    queryFn: async () => (await listPartitions()).partitions,
  });
}

/** The partition's directory, recursively — one read for the whole tree, as
 * the skill file browser does: a partition holds tens of files, not a repo. */
export function usePartitionFiles(partitionUid: string) {
  return useQuery({
    queryKey: memoryPartitionFilesKey(partitionUid),
    queryFn: async () => (await listPartitionFiles(partitionUid)).root,
    enabled: partitionUid.length > 0,
  });
}

/** One file out of that directory, read-only. */
export function usePartitionFileContent(partitionUid: string, path: string | null) {
  return useQuery({
    queryKey: memoryPartitionFileKey(partitionUid, path ?? ""),
    queryFn: () => readPartitionFile(partitionUid, path as string),
    enabled: Boolean(partitionUid && path),
  });
}

/** Read the agents' native memory now. Partitions, note counts and every
 * partition's files can all change, so the invalidation is the full
 * `["memory"]` prefix — same breadth as knowledge's curation. */
export function useSyncMemory() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: sync,
    onSuccess: (result) => {
      invalidateMemory(qc);
      toast.success(
        t("memory.syncDone", {
          count: result.entries_written,
          partitions: result.partitions.length,
        }),
      );
      if (result.failures.length > 0) {
        toast.error(t("memory.syncFailures", { count: result.failures.length }));
      }
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** Distil one partition: route this round's raw entries onto Coffer's own
 * notes — merge, open, retire or keep nothing — and rewrite its index.
 *
 * The pass is long and the daemon refuses a second one over the same
 * partition, so this hook keeps the shared run list honest at both ends: it
 * refreshes on settle (the spinner clears as soon as the pass is gone) and it
 * treats a 409 as "already running" rather than an error. A 409 is not a
 * failure the user needs told about — it is the state the button should
 * already have been showing, so refreshing the run list is the whole
 * response. */
export function useDistilPartition(partitionUid: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: () => distil(partitionUid),
    onSuccess: () => {
      invalidateMemory(qc);
      toast.success(t("memory.detail.distilDone"));
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "UPKEEP_ALREADY_RUNNING") return;
      toast.error(translateApiError(t, error));
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: upkeepRunsKey }),
  });
}

/** Per-agent delivery state — whether Coffer's hook is installed in that
 * agent's own settings (see "Show delivery state on the agent's own page"). Whether it has ever
 * fired is a separate question, answered by the audit surface. Omit `agentUid` to list every agent
 * delivery can install for.
 *
 * Each row carries the agent's name beside its uid, so a surface renders the
 * name and acts on the uid without a second request. */
export function useMemoryDelivery(agentUid?: string) {
  return useQuery({
    queryKey: agentUid ? memoryAgentDeliveryKey(agentUid) : memoryDeliveryKey,
    queryFn: async () => (await listDelivery(agentUid)).delivery,
  });
}

export function useInstallDelivery() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (agentUid: string) => installDelivery(agentUid),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: memoryDeliveryKey });
      toast.success(t("memory.delivery.installDone"));
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** Removal only takes out Coffer's own marker-scoped entry — nothing else in
 * the agent's own settings file is touched (spec memory "Install delivery hooks
 * explicitly and removably"). */
export function useRemoveDelivery() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (agentUid: string) => removeDelivery(agentUid),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: memoryDeliveryKey });
      toast.success(t("memory.delivery.removeDone"));
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
