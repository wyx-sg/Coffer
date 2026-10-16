// frontend/src/lib/hooks/useMemory.ts
//
// ALL queries + mutations for the memory sync (agents/frontend.md §3; spec
// memory "Manage memory sync in the web UI and on the command line"). Keys are hierarchical under one
// `["memory"]` root, so a sync, a write or an undo — each of which can change
// every count on the page and every project's copy states — invalidates the
// whole subtree with one prefix. The sync's switch and interval are the
// internal engine's `memory_sync` pass (`useSetUpkeep`), whose last and next
// run are refreshed with it.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import {
  cancelPreview,
  curationHandoff,
  enableCuration,
  getEntry,
  getSyncState,
  listEntries,
  runSync,
  setCodexImport,
  undoSync,
  writePreview,
  type MemorySyncReport,
} from "@/lib/api/memory";
import {
  internalEngineKey,
  memoryEntriesKey,
  memoryEntryKey,
  memoryKey,
  memorySyncStateKey,
} from "@/lib/api/queryKeys";
import { useOpenInTerminal } from "@/lib/hooks/useTerminals";
import { parseSummary } from "@/lib/memory/syncFacts";

/** How often the state is re-read while a sync runs (the worker's or another tab's). */
const POLL_WHILE_RUNNING_MS = 1500;

export function useMemorySyncState() {
  return useQuery({
    queryKey: memorySyncStateKey,
    queryFn: getSyncState,
    refetchInterval: (query) => (query.state.data?.running ? POLL_WHILE_RUNNING_MS : false),
  });
}

/** One project's memories (`""`: global ones), each with where it was written here. */
export function useMemoryEntries(project: string | null) {
  return useQuery({
    queryKey: memoryEntriesKey(project ?? ""),
    queryFn: async () => (await listEntries(project ?? "")).entries,
    enabled: project !== null,
  });
}

/** One memory's text and where each agent holds it; `null` reads nothing. */
export function useMemoryEntry(id: string | null) {
  return useQuery({
    queryKey: memoryEntryKey(id ?? ""),
    queryFn: () => getEntry(id ?? ""),
    enabled: id !== null,
  });
}

/** Refresh everything a sync can change: the page, every project, the pass's clock. */
function useInvalidateSync() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: memoryKey });
    void qc.invalidateQueries({ queryKey: internalEngineKey });
  };
}

/** The toast after a sync or a Write: what changed, or that copies wait for review. */
function useReportToast() {
  const { t } = useTranslation();
  const { toast } = useToast();
  return (report: MemorySyncReport) => {
    const s = parseSummary(report.summary);
    if (s.preview) {
      toast.info(t("memory.toast.previewWaiting"));
      return;
    }
    const changed = s.published + s.updated + s.deleted + s.written + s.removed;
    if (changed === 0) {
      toast.success(t("memory.toast.nothingChanged"));
      return;
    }
    toast.success(t("memory.toast.synced"), {
      description: t("memory.toast.syncedDetail", {
        published: s.published + s.updated,
        written: s.written,
        removed: s.removed,
      }),
    });
  };
}

/** Sync now. A sync already running is refused (`MEMORY_SYNC_RUNNING`), said in a toast. */
export function useSyncNow() {
  const invalidate = useInvalidateSync();
  const report = useReportToast();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: runSync,
    onSuccess: report,
    onError: (error) => toast.error(translateApiError(t, error)),
    onSettled: invalidate,
  });
}

/** Write the pending preview: exactly the copies it listed. */
export function useWritePreview() {
  const invalidate = useInvalidateSync();
  const report = useReportToast();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: writePreview,
    onSuccess: report,
    onError: (error) => toast.error(translateApiError(t, error)),
    onSettled: invalidate,
  });
}

/** Cancel the pending preview: nothing is written; the next sync plans again. */
export function useCancelPreview() {
  const invalidate = useInvalidateSync();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: cancelPreview,
    onError: (error) => toast.error(translateApiError(t, error)),
    onSettled: invalidate,
  });
}

/** Undo sync…: remove Coffer's copies from this machine's agents and turn automatic sync off.
 *
 *  No `onError` toast: it runs from a ConfirmDialog, which stays open and shows the failure itself. */
export function useUndoSync() {
  const invalidate = useInvalidateSync();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: undoSync,
    onSuccess: (report) => {
      const s = parseSummary(report.summary);
      toast.success(t("memory.undo.done", { count: s.removed }));
      invalidate();
    },
  });
}

/** Whether Codex imports Claude Code's memories itself (`null` forgets the answer). */
export function useSetCodexImport() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (value: boolean | null) => setCodexImport(value),
    onSuccess: () => void qc.invalidateQueries({ queryKey: memoryKey }),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** Turn on the agent's own curation in its settings; the state is re-read. */
export function useEnableCuration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (agentType: string) => enableCuration(agentType),
    onSuccess: () => void qc.invalidateQueries({ queryKey: memoryKey }),
  });
}

/** Curate now: the agent opens in the person's terminal with the daemon's
 *  prompt to consolidate its memory, so they watch and confirm each change. */
export function useCurateNow() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const openTerminal = useOpenInTerminal();
  return useMutation({
    mutationFn: async (agentType: string) => {
      const prompt = (await curationHandoff(agentType)).handoff.prompt;
      await openTerminal(
        { agent: agentType, prompt },
        {
          label: t("handoff.copyPrompt"),
          onClick: () => void navigator.clipboard?.writeText(prompt),
        },
      );
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
