// frontend/src/lib/hooks/useKnowledgeHistory.ts
//
// The queries and mutations over knowledge's HISTORY — the vault's git log read
// as changes (spec knowledge "Keep every document's history and undo a pass as
// a whole"): the cross-collection timeline Recent changes shows, one change in
// full, a document's versions and one version's diff, and the two writes that
// put the past back — restoring a version and undoing a curation pass. Both
// write a NEW version naming the user; nothing here rewrites what happened.
//
// Kept apart from `useKnowledge.ts` only for size (one hook file per feature is
// the rule, .agents/frontend.md §2; this is its second half). Every key hangs
// off `["knowledge"]`, so a curation pass or a save that invalidates the
// knowledge prefix refreshes the timeline and the open History tab with it.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import {
  getChange,
  getHistory,
  getVersionDiff,
  listChanges,
  restoreVersion,
  undoPass,
} from "@/lib/api/knowledge";
import {
  knowledgeChangeKey,
  knowledgeChangesKey,
  knowledgeFileKey,
  knowledgeHistoryKey,
  knowledgeKey,
  knowledgeVersionDiffKey,
} from "@/lib/api/queryKeys";

/** How many changes the timeline reads: the API's ceiling, then narrowed to
 *  the last seven days on the page. */
const TIMELINE_LIMIT = 200;

/** Recent changes across every collection (`null`) or one (its NAME), with
 *  the items still waiting in each inbox. */
export function useKnowledgeChanges(collection: string | null, enabled = true) {
  return useQuery({
    queryKey: knowledgeChangesKey(collection),
    queryFn: () => listChanges({ collection, limit: TIMELINE_LIMIT }),
    enabled,
  });
}

/** One change in full: every document it touched, each with its diff. */
export function useKnowledgeChange(version: string | null) {
  return useQuery({
    queryKey: knowledgeChangeKey(version ?? ""),
    queryFn: () => getChange(version as string),
    enabled: Boolean(version),
  });
}

/** A document's versions, newest first. No retry: a history that cannot be
 *  read says so in its tab at once, with its own Retry. */
export function useDocumentHistory(path: string | null) {
  return useQuery({
    queryKey: knowledgeHistoryKey(path ?? ""),
    queryFn: () => getHistory(path as string),
    enabled: Boolean(path),
    retry: false,
  });
}

/** What one version did to a document. */
export function useVersionDiff(path: string | null, version: string | null) {
  return useQuery({
    queryKey: knowledgeVersionDiffKey(path ?? "", version ?? ""),
    queryFn: () => getVersionDiff(path as string, version as string),
    enabled: Boolean(path && version),
  });
}

/**
 * Put one version of a document back, as a new version naming the user. The
 * restored body goes straight into the file's cache entry, and the rest of the
 * knowledge subtree — its History, the timeline, the tree — is invalidated.
 */
export function useRestoreVersion() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (input: { path: string; version: string }) => restoreVersion(input),
    onSuccess: (file) => {
      qc.setQueryData(knowledgeFileKey(file.path), file);
      void qc.invalidateQueries({ queryKey: knowledgeKey });
      toast.success(t("knowledge.history.restored"));
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/**
 * Undo a curation pass as a whole. No `onError` toast: the only caller is the
 * undo dialog, which says in place which document was changed since and
 * stays open (a refusal writes nothing).
 */
export function useUndoPass() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (version: string) => undoPass(version),
    onSuccess: () => void qc.invalidateQueries({ queryKey: knowledgeKey }),
  });
}
