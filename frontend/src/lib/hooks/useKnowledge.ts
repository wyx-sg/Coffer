// frontend/src/lib/hooks/useKnowledge.ts
//
// ALL queries + mutations for the `knowledge` kind, so the page, the trees and
// the viewer stay thin views (agents/frontend.md §3). The keys are
// hierarchical under one `["knowledge"]` root, so a write can invalidate the
// whole subtree with a prefix — each lane is fetched one directory per key and
// a curation pass may rewrite any level of `topics/`.
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

/** One level of ONE lane. Each expanded directory mounts its own query. */
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
 * Run ONE curation pass over one collection. It rewrites `topics/` — writing
 * new documents, retiring ones whose content moved — and stamps the source it
 * consumed, so every cached level and body under `["knowledge"]` is
 * invalidated afterwards.
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
    mutationFn: (source?: string | null) => curateCollection(collectionUid, source),
    onSuccess: (result) => {
      void qc.invalidateQueries({ queryKey: knowledgeKey });
      toast.success(t(`knowledge.detail.curateStatus.${result.status}`));
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "UPKEEP_ALREADY_RUNNING") return;
      toast.error(translateApiError(t, error));
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: upkeepRunsKey }),
  });
}

/**
 * Delete ONE source from a collection. The daemon refuses a `topics/` path,
 * and the page only ever offers the button on a source (FR-027).
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
 * Convert one uploaded document into a source. TWO files land — the original
 * and the Markdown extracted from it — at any level under the collection's
 * `sources/`, and its ancestors' counts all change with them, so success
 * invalidates the whole `["knowledge"]` subtree rather than guessing which
 * single level to refresh.
 */
export function useUploadKnowledgeFile() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    // `collection` is the collection's NAME here, not its uid: an upload lands
    // a file in a directory, and the directory is named after the collection.
    mutationFn: (vars: { collection: string; folder?: string | null; file: File }) =>
      uploadFile(vars),
    onSuccess: () => void qc.invalidateQueries({ queryKey: knowledgeKey }),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
