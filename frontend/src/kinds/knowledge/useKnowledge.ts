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
  getIndexStatus,
  getTree,
  listCollections,
  rebuildIndex,
  search,
  tidyCollection,
  uploadFile,
} from "./api";
import type { SearchOut } from "./types";

export const knowledgeKey = ["knowledge"] as const;
export const collectionsKey = () => [...knowledgeKey, "collections"] as const;
/** One directory level; `path` is relative to the knowledge root. */
export const treeKey = (path: string) => [...knowledgeKey, "tree", path] as const;
export const fileKey = (path: string) => [...knowledgeKey, "file", path] as const;
/** The disposable sidecar's status — one global query, not per-collection. */
export const indexKey = () => [...knowledgeKey, "index"] as const;

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

/**
 * Ranked (or literal-fallback) search over one collection. Modelled as a
 * mutation rather than a query: it runs when the user submits, not whenever
 * its inputs change, and the answer is never cached — a stale ranked result
 * would defeat the point of it being ranked.
 */
export function useKnowledgeSearch() {
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation<SearchOut, unknown, { query: string; collection?: string | null }>({
    mutationFn: (vars) => search(vars.query, vars.collection),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** The disposable sidecar's status: available/staleness, read on the page load. */
export function useIndexStatus() {
  return useQuery({
    queryKey: indexKey(),
    queryFn: getIndexStatus,
  });
}

/**
 * Re-embed every visible file from scratch. Runs synchronously on the
 * backend (the mutation's own `isPending` IS the "running" state — there is
 * no separate progress poll), and its answer is the freshest status there is,
 * so it seeds the cache directly rather than merely invalidating it.
 */
export function useRebuildIndex() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: rebuildIndex,
    onSuccess: (data) => {
      qc.setQueryData(indexKey(), data);
      toast.success(t("knowledge.index.rebuildDone"));
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
