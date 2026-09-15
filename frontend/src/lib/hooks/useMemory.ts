// frontend/src/lib/hooks/useMemory.ts
//
// ALL queries + mutations for the `memory` kind (agents/frontend.md §3). Keys
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
import { translateApiError } from "@/lib/api/errors";
import {
  getFact,
  installDelivery,
  listDelivery,
  listFacts,
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
  memoryFactKey,
  memoryFactsKey,
  memoryKey,
  memoryPartitionFileKey,
  memoryPartitionFilesKey,
  memoryPartitionsKey,
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

/** One partition's facts. */
export function useMemoryFacts(partition: string, enabled = true) {
  return useQuery({
    queryKey: memoryFactsKey(partition),
    queryFn: async () => (await listFacts(partition)).facts,
    enabled: enabled && partition.length > 0,
  });
}

/** One fact in full, with its own words and its origins. */
export function useMemoryFact(partition: string, slug: string | null) {
  return useQuery({
    queryKey: memoryFactKey(partition, slug ?? ""),
    queryFn: () => getFact(partition, slug as string),
    enabled: Boolean(partition && slug),
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
 * partition's digest. */
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
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** Per-agent delivery state — whether installed, and when it last actually
 * fired (FR-055). Omit `agent` to list every agent delivery can install for. */
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
 * the agent's own settings file is touched (spec memory FR-054). */
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
