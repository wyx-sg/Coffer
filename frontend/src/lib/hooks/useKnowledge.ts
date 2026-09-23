// frontend/src/lib/hooks/useKnowledge.ts
//
// ALL queries + mutations for the `knowledge` kind, so the page, the trees and
// the viewer stay thin views (agents/frontend.md §3). The keys are
// hierarchical under one `["knowledge"]` root, so a write can invalidate the
// whole subtree with a prefix — the tree is fetched one directory per key and a
// curation pass may rewrite any level of it.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { ApiError, translateApiError } from "@/lib/api/errors";
import {
  createCollection,
  curateCollection,
  deleteFile,
  getFile,
  getTree,
  listCollections,
  uploadFile,
} from "@/lib/api/knowledge";
import {
  knowledgeCollectionsKey,
  knowledgeFileKey,
  knowledgeKey,
  knowledgeTreeKey,
  upkeepRunsKey,
} from "@/lib/api/queryKeys";

// re-exported for tests that still import the root key from here; import
// from queryKeys directly in new code
export { knowledgeKey } from "@/lib/api/queryKeys";

export function useKnowledgeCollections() {
  return useQuery({
    queryKey: knowledgeCollectionsKey,
    queryFn: async () => (await listCollections()).collections,
  });
}

export function useCreateCollection() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (input: { name: string; description?: string | null }) => createCollection(input),
    onSuccess: () => void qc.invalidateQueries({ queryKey: knowledgeCollectionsKey }),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** One level of a collection's tree. Each expanded directory mounts its own query. */
export function useKnowledgeTree(path: string, enabled = true) {
  return useQuery({
    queryKey: knowledgeTreeKey(path),
    queryFn: () => getTree(path),
    enabled: enabled && path.length > 0,
  });
}

export function useKnowledgeFile(path: string | null) {
  return useQuery({
    queryKey: knowledgeFileKey(path ?? ""),
    queryFn: () => getFile(path as string),
    enabled: Boolean(path),
  });
}

/**
 * Run ONE curation pass over one collection. It rewrites the collection's
 * documents — writing new ones, retiring ones whose content moved — and drains
 * the inbox item it merged (or, with no model, promotes the whole inbox), so
 * every cached level, body and count under `["knowledge"]` is invalidated
 * afterwards.
 *
 * Every status the pass reports is a 200, so the toast says which one it was
 * rather than treating `no_model` or `up_to_date` as a success that did
 * something (FR-038).
 *
 * The pass is long and the daemon refuses a second one over the same
 * collection, so this keeps the shared run list honest at both ends — same
 * treatment as memory's organise. A 409 gets NO toast on purpose: the button
 * reads it off `mutation.error` and says a pass is already running in place,
 * where the click was, instead of the page saying it twice.
 */
export function useCurateCollection(collectionUid: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (document?: string | null) => curateCollection(collectionUid, document),
    onSuccess: (result) => {
      void qc.invalidateQueries({ queryKey: knowledgeKey });
      // `count` only means something to `no_model`, which reports how much of
      // the inbox it promoted to documents as it stood.
      toast.success(
        t(`knowledge.detail.curateStatus.${result.status}`, { count: result.promoted.length }),
      );
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "UPKEEP_ALREADY_RUNNING") return;
      toast.error(translateApiError(t, error));
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: upkeepRunsKey }),
  });
}

/**
 * Delete ONE document from a collection — any document, whoever wrote it
 * (FR-020).
 *
 * The deleted file's own cache entry is REMOVED rather than invalidated: a
 * viewer still mounted on it would otherwise refetch a path that is now a 404
 * and replace the page with an error. Its ancestors' counts all change with
 * it, so the rest of the `["knowledge"]` subtree is invalidated — the same
 * breadth as an upload, and for the same reason.
 *
 * No `onError` toast, against the default (agents/frontend.md §5): the only
 * caller is a ConfirmDialog, which renders the failure in place and stays open
 * so it can be read. A toast would say the same thing twice.
 */
export function useDeleteKnowledgeFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (path: string) => deleteFile(path),
    onSuccess: (_result, path) => {
      qc.removeQueries({ queryKey: knowledgeFileKey(path) });
      void qc.invalidateQueries({ queryKey: knowledgeKey });
    },
  });
}

/**
 * Convert one uploaded document into material for a collection. It either
 * waits in the inbox (the collection's `pending_count` goes up) or becomes a
 * document on the spot (a tree level and `document_count` change), so success
 * invalidates the whole `["knowledge"]` subtree rather than guessing which of
 * the two happened. Which one it was is the caller's toast to report.
 */
export function useUploadKnowledgeFile() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    // `collection` is the collection's NAME here, not its uid: an upload lands
    // material in a directory, and the directory is named after the collection.
    mutationFn: (vars: { collection: string; file: File }) => uploadFile(vars),
    onSuccess: () => void qc.invalidateQueries({ queryKey: knowledgeKey }),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
