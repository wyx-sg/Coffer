// frontend/src/kinds/knowledge/useKnowledge.ts
//
// ALL queries + mutations for the `knowledge` kind, so the page, the tree and
// the viewer stay thin views (agents/frontend.md §3). The keys are
// hierarchical under one `["knowledge"]` root, so a write can invalidate the
// whole subtree with a prefix — the tree is fetched one directory per key and
// a tidy pass may touch any of them.
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
  tidyCollection,
} from "./api";

export const knowledgeKey = ["knowledge"] as const;
export const collectionsKey = () => [...knowledgeKey, "collections"] as const;
/** One directory level; `path` is relative to the knowledge root. */
export const treeKey = (path: string) => [...knowledgeKey, "tree", path] as const;
export const fileKey = (path: string) => [...knowledgeKey, "file", path] as const;

export function useKnowledgeCollections() {
  return useQuery({
    queryKey: collectionsKey(),
    queryFn: async () => (await listCollections()).collections,
  });
}

export function useCreateCollection() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (input: { name: string; description?: string | null }) => createCollection(input),
    onSuccess: () => void qc.invalidateQueries({ queryKey: collectionsKey() }),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** One level of the catalogue. Each expanded directory mounts its own query. */
export function useKnowledgeTree(path: string, enabled = true) {
  return useQuery({
    queryKey: treeKey(path),
    queryFn: () => getTree(path),
    enabled: enabled && path.length > 0,
  });
}

export function useKnowledgeFile(path: string | null) {
  return useQuery({
    queryKey: fileKey(path ?? ""),
    queryFn: () => getFile(path as string),
    enabled: Boolean(path),
  });
}

/**
 * Delete one file. The detail view of the deleted path is REMOVED rather than
 * invalidated, so a stale preview can't refetch a 404, and the whole tree is
 * invalidated because the parent level's listing and file counts both change.
 */
export function useDeleteKnowledgeFile() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (path: string) => deleteFile(path),
    onSuccess: (_data, path) => {
      qc.removeQueries({ queryKey: fileKey(path) });
      void qc.invalidateQueries({ queryKey: knowledgeKey });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/**
 * Run the tidy pass over one collection. It merges and rewrites files in
 * place (archiving each prior revision into `.history/` first), so every
 * cached level and body under `["knowledge"]` is invalidated afterwards.
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
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
