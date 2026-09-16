// frontend/src/lib/hooks/useMemory.ts
//
// ALL queries + mutations for the `memory` kind (.agents/frontend.md §3). Keys
// are hierarchical under one `["memory"]` root so a write with cross-cutting
// effects — a sync, an organise pass — can invalidate the whole subtree with a
// prefix, mirroring `lib/hooks/useKnowledge.ts`.
//
// A partition's file keys hang off that partition's own key rather than a
// sibling root, because a sync or organise pass rewrites the files on disk:
// nesting them means the broad invalidation those mutations already do
// reaches the open preview too, with no key threaded through by hand.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { ApiError, translateApiError } from "@/lib/api/errors";
import {
  installDelivery,
  listDelivery,
  listPartitionFiles,
  listPartitions,
  organise,
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

/** Aggregation and the organise pass both rewrite whole partitions on disk —
 * partition list, fact counts and every file under them — so both invalidate
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
export function usePartitionFiles(partition: string) {
  return useQuery({
    queryKey: memoryPartitionFilesKey(partition),
    queryFn: async () => (await listPartitionFiles(partition)).root,
    enabled: partition.length > 0,
  });
}

/** One file out of that directory, read-only. */
export function usePartitionFileContent(partition: string, path: string | null) {
  return useQuery({
    queryKey: memoryPartitionFileKey(partition, path ?? ""),
    queryFn: () => readPartitionFile(partition, path as string),
    enabled: Boolean(partition && path),
  });
}

/** Read the agents' native memory now. Partitions, fact counts and every
 * partition's files can all change, so the invalidation is the full
 * `["memory"]` prefix — same breadth as knowledge's tidy. */
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
          count: result.facts_written,
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

/** Merge duplicates, propose supersessions/conflicts and rewrite one
 * partition's digest.
 *
 * The pass is long and the daemon refuses a second one over the same
 * partition, so this hook keeps the shared run list honest at both ends: it
 * refreshes on settle (the spinner clears as soon as the pass is gone) and it
 * treats a 409 as "already running" rather than an error. A 409 is not a
 * failure the user needs told about — it is the state the button should
 * already have been showing, so refreshing the run list is the whole
 * response. */
export function useOrganisePartition(partition: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: () => organise(partition),
    onSuccess: () => {
      invalidateMemory(qc);
      toast.success(t("memory.detail.organiseDone"));
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "UPKEEP_ALREADY_RUNNING") return;
      toast.error(translateApiError(t, error));
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: upkeepRunsKey }),
  });
}

/** Per-agent delivery state — whether installed, and when it last actually
 * fired (FR-026). Omit `agent` to list every agent delivery can install for. */
export function useMemoryDelivery(agent?: string) {
  return useQuery({
    queryKey: agent ? memoryAgentDeliveryKey(agent) : memoryDeliveryKey,
    queryFn: async () => (await listDelivery(agent)).delivery,
  });
}

export function useInstallDelivery() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (agent: string) => installDelivery(agent),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: memoryDeliveryKey });
      toast.success(t("memory.delivery.installDone"));
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** Removal only takes out Coffer's own marker-scoped entry — nothing else in
 * the agent's own settings file is touched (spec memory FR-025). */
export function useRemoveDelivery() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (agent: string) => removeDelivery(agent),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: memoryDeliveryKey });
      toast.success(t("memory.delivery.removeDone"));
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
