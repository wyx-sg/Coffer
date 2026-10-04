// frontend/src/lib/hooks/useKnowledgeHistory.ts
//
// The queries and mutations over knowledge's HISTORY — the vault's git log read
// as changes (spec knowledge "Keep every document's history"): the
// cross-collection timeline Recent changes shows, a
// document's versions and one version's diff, and the writes that put the past
// back — restoring a version or a deleted document. Both write a NEW version
// naming the user; nothing here rewrites what happened.
//
// Kept apart from `useKnowledge.ts` only for size (one hook file per feature is
// the rule, .agents/frontend.md §2; this is its second half). Every key hangs
// off `["knowledge"]`, so a write that invalidates the
// knowledge prefix refreshes the timeline and the open History tab with it.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import {
  describeCollection,
  getHistory,
  getVersionBody,
  getVersionDiff,
  listChanges,
  restoreDeleted,
  restoreVersion,
} from "@/lib/api/knowledge";
import {
  knowledgeChangesKey,
  knowledgeFileKey,
  knowledgeHistoryKey,
  knowledgeKey,
  knowledgeVersionBodyKey,
  knowledgeVersionDiffKey,
} from "@/lib/api/queryKeys";

/** How many changes the timeline reads: the API's ceiling, then narrowed to
 *  the last seven days on the page. */
const TIMELINE_LIMIT = 200;

/** Recent changes across every collection (`null`) or one (its NAME). */
export function useKnowledgeChanges(collection: string | null, enabled = true) {
  return useQuery({
    queryKey: knowledgeChangesKey(collection),
    queryFn: () => listChanges({ collection, limit: TIMELINE_LIMIT }),
    enabled,
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

/** A document's body as one version left it — Compare with current sets it
 *  against the document as it is now. */
export function useVersionBody(path: string | null, version: string | null, enabled = true) {
  return useQuery({
    queryKey: knowledgeVersionBodyKey(path ?? "", version ?? ""),
    queryFn: () => getVersionBody(path as string, version as string),
    enabled: enabled && Boolean(path && version),
  });
}

/**
 * Put one version of a document back, as a new version naming the user. The
 * restored body goes straight into the file's cache entry, and the rest of the
 * knowledge subtree — its History, the timeline, the tree — is invalidated.
 * The caller toasts the success (it names the version's date); a refusal is
 * toasted here.
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
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/**
 * Put back what a delete removed — a document, or a whole collection with its
 * documents and README (spec knowledge "Restore a deleted
 * collection or document from Recent changes"). No `onError` toast: Recent
 * changes says in place, on the row, why a restore was refused (the path or
 * the collection's name is taken again).
 */
export function useRestoreDeleted() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (version: string) => restoreDeleted(version),
    onSuccess: () => void qc.invalidateQueries({ queryKey: knowledgeKey }),
  });
}

/** Rewrite a collection's description — its README's opening paragraph. A
 *  collection has no title; this is the one thing about it a person edits
 *  here besides its documents. */
export function useDescribeCollection(uid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (description: string) => describeCollection(uid, description),
    onSuccess: () => void qc.invalidateQueries({ queryKey: knowledgeKey }),
  });
}
