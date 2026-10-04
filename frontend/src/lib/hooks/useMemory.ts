// frontend/src/lib/hooks/useMemory.ts
//
// ALL queries + mutations for the `memory` kind (agents/frontend.md §3). Keys
// are hierarchical under one `["memory"]` root so a write with cross-cutting
// effects — Update memory, a distil pass — can invalidate the whole subtree
// with a prefix, mirroring `lib/hooks/useKnowledge.ts`.
//
// A partition's memories, retired memories, files and delivered text hang off
// that partition's own key, so the broad invalidation Update memory does
// reaches the open partition page too, and deleting a partition can drop its
// whole subtree in one `removeQueries`.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import {
  deleteNote,
  getDelivered,
  getNote,
  getReading,
  listNotes,
  listPartitions,
  listRetired,
  saveNote,
  sync,
} from "@/lib/api/memory";
import {
  memoryDeliveredKey,
  memoryKey,
  memoryNoteKey,
  memoryNotesKey,
  memoryPartitionFilesKey,
  memoryPartitionsKey,
  memoryReadingKey,
  memoryRetiredKey,
  resourcesKey,
  upkeepRunsKey,
} from "@/lib/api/queryKeys";
import { resourcesApi } from "@/lib/api/resources";

export function useMemoryPartitions() {
  return useQuery({
    queryKey: memoryPartitionsKey,
    queryFn: async () => (await listPartitions()).partitions,
  });
}

/** A partition's memories, newest wording as the last distil pass left them. */
export function useMemoryNotes(uid: string) {
  return useQuery({
    queryKey: memoryNotesKey(uid),
    queryFn: async () => (await listNotes(uid)).notes,
    enabled: uid.length > 0,
  });
}

/** One memory in full: body (frontmatter stripped by the daemon) + provenance. */
export function useMemoryNote(uid: string, slug: string | null) {
  return useQuery({
    queryKey: memoryNoteKey(uid, slug ?? ""),
    queryFn: () => getNote(uid, slug as string),
    enabled: Boolean(uid && slug),
  });
}

/** Save one memory's body (spec memory "Edit a memory in the
 *  web UI or in an editor"). Resolves with the new fingerprint, so the editor's next save does
 *  not conflict with its own previous one. The saved note replaces the cached
 *  read, so the page shows the new body and update time at once; the list and
 *  the partition rows (newest update) are refetched. A refused save is the
 *  editor's to show, so there is no toast. */
export function useSaveMemoryNote(uid: string, slug: string) {
  const qc = useQueryClient();
  return useCallback(
    async (body: string, expectedFingerprint: string): Promise<string> => {
      const saved = await saveNote(uid, slug, { body, expected_fingerprint: expectedFingerprint });
      qc.setQueryData(memoryNoteKey(uid, slug), saved);
      void qc.invalidateQueries({ queryKey: memoryNotesKey(uid) });
      void qc.invalidateQueries({ queryKey: memoryPartitionsKey });
      return saved.fingerprint;
    },
    [qc, uid, slug],
  );
}

/** Delete one memory by hand (spec memory "Delete a memory by hand"). The
 *  memory's own read is dropped before the lists refetch, so the pane that
 *  showed it cannot refetch a 404; the list falls to the next memory and the
 *  deleted one shows in the Retired group.
 *
 *  No `onError` toast: it runs from a ConfirmDialog, which stays open and shows
 *  the failure itself. */
export function useDeleteMemoryNote(uid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => deleteNote(uid, slug),
    onSuccess: (_data, slug) => {
      qc.removeQueries({ queryKey: memoryNoteKey(uid, slug) });
      void qc.invalidateQueries({ queryKey: memoryNotesKey(uid) });
      void qc.invalidateQueries({ queryKey: memoryRetiredKey(uid) });
      void qc.invalidateQueries({ queryKey: memoryPartitionsKey });
      void qc.invalidateQueries({ queryKey: memoryPartitionFilesKey(uid) });
      void qc.invalidateQueries({ queryKey: memoryDeliveredKey(uid) });
    },
  });
}

/** The memories the partition retired, each with its reason. */
export function useMemoryRetired(uid: string) {
  return useQuery({
    queryKey: memoryRetiredKey(uid),
    queryFn: async () => (await listRetired(uid)).retired,
    enabled: uid.length > 0,
  });
}

/** The exact session-start text each connected agent receives in the
 *  partition's project. */
export function useMemoryDelivered(uid: string) {
  return useQuery({
    queryKey: memoryDeliveredKey(uid),
    queryFn: async () => (await getDelivered(uid)).agents,
    enabled: uid.length > 0,
  });
}

/** When the agents' memory was last read, and whose read failed — the
 *  Memory header's "Read 14 min ago" and its failure banner (spec memory
 *  "Report the last read of the agents' memory"). */
export function useMemoryReading() {
  return useQuery({ queryKey: memoryReadingKey, queryFn: getReading });
}

/** Update memory: read every agent's latest native memory, then distil every
 * partition that gained new entries (spec memory "Update memory in one
 * action"). Partitions, memories and every partition's files can all change,
 * so the invalidation is the full `["memory"]` prefix.
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
      void qc.invalidateQueries({ queryKey: memoryKey });
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

/** Delete a partition whose repository is gone (spec memory "Report
 * unresolvable partitions") through the kind-agnostic resource route. The
 * partition's own sub-queries are removed before the list is invalidated, so an
 * open partition page cannot refetch a 404.
 *
 * No `onError` toast: the one place this runs is a ConfirmDialog, which stays
 * open and shows the failure itself. */
export function useDeletePartition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uid: string) => resourcesApi.remove(uid),
    onSuccess: (_data, uid) => {
      for (const key of [
        memoryNotesKey(uid),
        memoryRetiredKey(uid),
        memoryPartitionFilesKey(uid),
        memoryDeliveredKey(uid),
      ]) {
        qc.removeQueries({ queryKey: key });
      }
      void qc.invalidateQueries({ queryKey: memoryPartitionsKey });
      void qc.invalidateQueries({ queryKey: resourcesKey });
    },
  });
}
