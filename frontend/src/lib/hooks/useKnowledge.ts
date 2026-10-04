// frontend/src/lib/hooks/useKnowledge.ts
//
// ALL queries + mutations for the `knowledge` kind, so the page, the trees and
// the viewer stay thin views (agents/frontend.md §3). The keys are
// hierarchical under one `["knowledge"]` root, so a write can invalidate the
// whole subtree with a prefix — the tree is fetched one directory per key and a
// write may change any level of it.
import { useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import {
  createCollection,
  deleteFile,
  getFile,
  getTree,
  listCollections,
  saveFile,
  uploadFile,
  type FileSave,
} from "@/lib/api/knowledge";
import {
  knowledgeChangesRootKey,
  knowledgeCollectionsKey,
  knowledgeFileKey,
  knowledgeHistoryKey,
  knowledgeKey,
  knowledgeTreeKey,
  knowledgeTreeRootKey,
} from "@/lib/api/queryKeys";
import { resourcesApi } from "@/lib/api/resources";

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

/**
 * Rename a collection: the kind-agnostic `PATCH /resources/{uid}` with the new
 * name, which moves the collection's folder with it. The whole `["knowledge"]`
 * subtree is refreshed, since tree levels, files and changes are keyed by the
 * folder path. No `onError` toast: the rename dialog shows the refusal (a name
 * taken or invalid) under its field and stays open.
 */
export function useRenameCollection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uid, name }: { uid: string; name: string }) => resourcesApi.rename(uid, name),
    onSuccess: () => void qc.invalidateQueries({ queryKey: knowledgeKey }),
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
 * The save the viewer's editor issues (see "Save a document edited in the web
 * UI"). It is a plain async function rather than a mutation because
 * `useFileDraft` owns the mutation — its pending state, its error and the 409
 * it turns into a conflict — and only needs something to call.
 *
 * On success the saved file goes straight into its cache entry, so the pane
 * renders the new body without waiting on a refetch, and every tree level is
 * invalidated: a document's title comes from its frontmatter. Resolves with
 * the new fingerprint, so a second save in the same session does not 409
 * against the first.
 *
 * No toast either way: `FileEditor` says "saved" itself and renders a refusal
 * in place, where the draft still is.
 */
export function useSaveKnowledgeFile() {
  const qc = useQueryClient();
  return useCallback(
    async (input: FileSave): Promise<string> => {
      const saved = await saveFile(input);
      qc.setQueryData(knowledgeFileKey(saved.path), saved);
      void qc.invalidateQueries({ queryKey: knowledgeTreeRootKey });
      // An accepted save is a commit naming the user: the document's History
      // and the timeline both gain it.
      void qc.invalidateQueries({ queryKey: knowledgeHistoryKey(saved.path) });
      void qc.invalidateQueries({ queryKey: knowledgeChangesRootKey });
      return saved.fingerprint;
    },
    [qc],
  );
}

/**
 * Delete ONE document from a collection — any document, whoever wrote it
 * (see "Let only a person delete a document").
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
 * Convert one uploaded document into a document of a collection (a tree level
 * and `document_count` change), so success invalidates the whole
 * `["knowledge"]` subtree. A refusal (an unsupported type, a file too large) is
 * rendered in the upload dialog, where the file still is — so no `onError`
 * toast here.
 */
export function useUploadKnowledgeFile() {
  const qc = useQueryClient();
  return useMutation({
    // `collection` is the collection's NAME here, not its uid: an upload lands
    // in a directory, and the directory is named after the collection.
    mutationFn: (vars: { collection: string; file: File; signal?: AbortSignal }) =>
      uploadFile(vars),
    onSuccess: () => void qc.invalidateQueries({ queryKey: knowledgeKey }),
  });
}
