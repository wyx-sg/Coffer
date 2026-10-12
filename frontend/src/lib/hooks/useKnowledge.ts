// frontend/src/lib/hooks/useKnowledge.ts
//
// ALL queries + mutations for the `knowledge` kind, so the page, the trees and
// the viewer stay thin views (agents/frontend.md §3). The keys are
// hierarchical under one `["knowledge"]` root, so a write can invalidate the
// whole subtree with a prefix — the tree is fetched one directory per key and a
// write may change any level of it.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import {
  createCollection,
  linkFolder,
  deleteFile,
  describeCollection,
  getCheck,
  getCollectionFiles,
  getAsset,
  getFile,
  getTree,
  listChanges,
  listCollections,
  undoChange,
  uploadFile,
  type ChangeOut,
} from "@/lib/api/knowledge";
import {
  knowledgeChangesKey,
  knowledgeCheckKey,
  knowledgeCollectionsKey,
  knowledgeAssetKey,
  knowledgeFileKey,
  knowledgeFilesKey,
  knowledgeKey,
  knowledgeTreeKey,
} from "@/lib/api/queryKeys";
import { resourcesApi } from "@/lib/api/resources";
import { useInfiniteList } from "@/lib/hooks/useInfiniteList";

/** Changes a collection's Change log reads at a time. */
const CHANGE_LOG_PAGE = 20;

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

/** Link a folder the person keeps themselves. No `onError` toast: the dialog
 * shows the refusal beside the folder. */
export function useLinkFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { folder: string; name?: string | null }) => linkFolder(input),
    onSuccess: () => void qc.invalidateQueries({ queryKey: knowledgeCollectionsKey }),
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

/** A picture a document shows, as a data URL (`null` when it is gone). */
export function useKnowledgeAsset(path: string) {
  return useQuery({
    queryKey: knowledgeAssetKey(path),
    queryFn: () => getAsset(path),
    staleTime: 60_000,
  });
}

/** A collection's mechanical check: its findings, read with the collection
 *  page and refreshed with everything else under `["knowledge"]`. */
export function useKnowledgeCheck(uid: string) {
  return useQuery({
    queryKey: knowledgeCheckKey(uid),
    queryFn: () => getCheck(uid),
  });
}

/** Every page and source of a collection, with its title, page type and
 *  waiting mark: its page's Contents, and the titles To do and the Change log
 *  name files by. */
export function useKnowledgeFiles(uid: string) {
  return useQuery({
    queryKey: knowledgeFilesKey(uid),
    queryFn: async () => (await getCollectionFiles(uid)).files,
  });
}

/**
 * Undo a change — a tidy's **Undo this tidy**: every file it touched put back,
 * as one new change. A refusal (`KNOWLEDGE_UNDO_CONFLICT`, files edited since)
 * is the caller's to show, with Undo anyway; so no `onError` toast here.
 */
export function useUndoChange() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ version, force = false }: { version: string; force?: boolean }) =>
      undoChange(version, force),
    onSuccess: () => void qc.invalidateQueries({ queryKey: knowledgeKey }),
  });
}

/** A collection's Change log: the changes feed for it (`collection` is its
 *  NAME), newest first, a page at a time. */
export function useKnowledgeChangeLog(collection: string) {
  return useInfiniteList<ChangeOut>({
    queryKey: knowledgeChangesKey(collection),
    fetchPage: async (cursor, signal) => {
      const page = await listChanges({ collection, limit: CHANGE_LOG_PAGE, cursor, signal });
      return { items: page.changes, next: page.next_cursor };
    },
  });
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
 * No `onError` toast, against the default (agents/frontend.md §5): the caller
 * (`useDeleteDocument`) toasts the refusal itself, with its details.
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
 * Convert one uploaded file into a source of a collection (a tree level, the
 * source and waiting counts and the check change), so success invalidates the whole
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

/** Rewrite a collection's description — its README's opening paragraph. A
 *  collection has no title; this is the one thing about it a person edits
 *  here besides uploading documents. */
export function useDescribeCollection(uid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (description: string) => describeCollection(uid, description),
    onSuccess: () => void qc.invalidateQueries({ queryKey: knowledgeKey }),
  });
}
