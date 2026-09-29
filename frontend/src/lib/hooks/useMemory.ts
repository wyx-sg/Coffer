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
import { translateApiError } from "@/lib/api/errors";
import {
  listPartitionFiles,
  listPartitions,
  readPartitionFile,
  sync,
} from "@/lib/api/memory";
import {
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

/** Update memory: read every agent's latest native memory, then distil every
 * partition that gained new entries (spec memory "Update memory in one
 * action"). Partitions, note counts and every partition's files can all
 * change, so the invalidation is the full `["memory"]` prefix — same breadth
 * as knowledge's curation.
 *
 * A distil pass already running over a partition does not fail the request —
 * the daemon reports that partition as skipped — and the shared run list is
 * refreshed on settle, so a partition page's spinner follows the daemon's
 * answer rather than this mutation's. */
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
          partitions: result.distilled.length,
        }),
      );
      if (result.failures.length > 0) {
        toast.error(t("memory.syncFailures", { count: result.failures.length }));
      }
    },
    onError: (error) => toast.error(translateApiError(t, error)),
    onSettled: () => void qc.invalidateQueries({ queryKey: upkeepRunsKey }),
  });
}
