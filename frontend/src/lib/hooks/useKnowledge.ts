// frontend/src/lib/hooks/useKnowledge.ts
//
// ALL queries + mutations for the `knowledge` kind, so the page, the tree and
// the viewer stay thin views (agents/frontend.md §3). The keys are
// hierarchical under one `["knowledge"]` root, so a write can invalidate the
// whole subtree with a prefix — the tree is fetched one directory per key and
// a tidy pass may touch any of them.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { ApiError, translateApiError } from "@/lib/api/errors";
import {
  createCollection,
  deleteFile,
  getFile,
  getTree,
  listCollections,
  tidyCollection,
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

/** One level of the catalogue. Each expanded directory mounts its own query. */
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
 * Run the tidy pass over one collection. It merges and rewrites files in
 * place (archiving each prior revision into `.history/` first), so every
 * cached level and body under `["knowledge"]` is invalidated afterwards.
 *
 * The pass is long and the daemon refuses a second one over the same
 * collection, so this keeps the shared run list honest at both ends — same
 * treatment as memory's organise. A 409 is not a failure worth a toast: it
 * means a pass is already running, which is what the button should already
 * have been showing, so refreshing the run list is the whole response.
 */
export function useTidyCollection(collection: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: () => tidyCollection(collection),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: knowledgeKey });
      toast.success(t("knowledge.detail.tidyDone"));
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "UPKEEP_ALREADY_RUNNING") return;
      toast.error(translateApiError(t, error));
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: upkeepRunsKey }),
  });
}

/**
 * Delete ONE file from a collection.
 *
 * The deleted file's own cache entry is REMOVED rather than invalidated: a
 * viewer still mounted on it would otherwise refetch a path that is now a 404
 * and replace the page with an error. Its ancestors' file counts all change
 * with it, so the rest of the `["knowledge"]` subtree is invalidated — the
 * same breadth as an upload, and for the same reason.
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
 * Convert one uploaded document into a knowledge file. The new file can land
 * at any level under the collection, and its ancestors' file counts all
 * change with it, so success invalidates the whole `["knowledge"]` subtree —
 * same breadth as tidy — rather than guessing which single level to refresh.
 */
export function useUploadKnowledgeFile() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (vars: { collection: string; directory?: string | null; file: File }) =>
      uploadFile(vars),
    onSuccess: () => void qc.invalidateQueries({ queryKey: knowledgeKey }),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
