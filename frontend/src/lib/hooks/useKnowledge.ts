// frontend/src/lib/hooks/useKnowledge.ts
//
// ALL queries + mutations for the `knowledge` kind, so the page, the trees and
// the viewer stay thin views (agents/frontend.md §3). The keys are
// hierarchical under one `["knowledge"]` root, so a write can invalidate the
// whole subtree with a prefix — the tree is fetched one directory per key and a
// curation pass may rewrite any level of it.
import { useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { TFunction } from "i18next";
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
  saveFile,
  submitMaterial,
  uploadFile,
  type CurationRunOut,
  type FileSave,
  type MaterialIn,
} from "@/lib/api/knowledge";
import {
  knowledgeChangesRootKey,
  knowledgeCollectionsKey,
  knowledgeFileKey,
  knowledgeHistoryKey,
  knowledgeKey,
  knowledgeTreeKey,
  knowledgeTreeRootKey,
  upkeepRunsKey,
} from "@/lib/api/queryKeys";
import { curateToastKey } from "@/lib/hooks/curateToast";

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
 * The save the viewer's editor issues (see "Save a document edited in the web
 * UI"). It is a plain async function rather than a mutation because
 * `useFileDraft` owns the mutation — its pending state, its error and the 409
 * it turns into a conflict — and only needs something to call.
 *
 * On success the saved file goes straight into its cache entry, so the pane
 * renders the new body without waiting on a refetch, and every tree level is
 * invalidated: a document's title comes from its frontmatter, and the next
 * sweep may rewrite the rest. Resolves with the new fingerprint, so a second
 * save in the same session does not 409 against the first.
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

/** The one toast a finished Curate now leaves: the last pass says how the run
 *  ended; `count` is how many items it curated (`ok`), or for `no_model` how
 *  many it wrote as documents as they stood. */
function curateToastText(t: TFunction, result: CurationRunOut) {
  const last = result.passes[result.passes.length - 1];
  const promoted = result.passes.reduce((sum, p) => sum + p.promoted.length, 0);
  const curated = result.passes.filter((p) => p.status === "ok").length;
  return t(last ? curateToastKey(last) : "knowledge.curate.status.up_to_date", {
    count: last?.status === "ok" ? curated : promoted,
  });
}

/**
 * Curate one collection now: passes one at a time until nothing is pending,
 * stopping at the first that fails (see "Run curation on a sweep and on
 * demand"). It rewrites the collection's documents and drains its inbox, so
 * every cached level, body, count and change under `["knowledge"]` is
 * invalidated afterwards. Progress (n of m) is the daemon's, on the in-flight
 * list (`useUpkeepRun`), so a page that remounts mid-run still shows it.
 *
 * A 409 gets NO toast on purpose: the control reads it off `mutation.error`
 * and says a pass is already running in place, where the click was.
 */
export function useCurateCollection(collectionUid: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (document?: string | null) => curateCollection(collectionUid, document),
    onSuccess: (result) => {
      void qc.invalidateQueries({ queryKey: knowledgeKey });
      toast.success(curateToastText(t, result));
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "UPKEEP_ALREADY_RUNNING") return;
      toast.error(translateApiError(t, error));
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: upkeepRunsKey }),
  });
}

/**
 * Curate several collections now, one after another — Recent changes' Curate
 * now over every collection with items waiting. A collection already being
 * curated is skipped rather than failing the rest; any other refusal stops
 * the run and is toasted.
 */
export function useCurateCollections() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: async (uids: string[]) => {
      const results: CurationRunOut[] = [];
      for (const uid of uids) {
        try {
          results.push(await curateCollection(uid, null));
        } catch (error) {
          if (error instanceof ApiError && error.code === "UPKEEP_ALREADY_RUNNING") continue;
          throw error;
        }
        void qc.invalidateQueries({ queryKey: upkeepRunsKey });
      }
      return results;
    },
    onSuccess: (results) => {
      void qc.invalidateQueries({ queryKey: knowledgeKey });
      const last = results[results.length - 1];
      if (last) toast.success(curateToastText(t, last));
    },
    onError: (error) => toast.error(translateApiError(t, error)),
    onSettled: () => void qc.invalidateQueries({ queryKey: upkeepRunsKey }),
  });
}

/**
 * Add a document: a title and body submitted as an ITEM into a collection's
 * inbox, curated like any other (see "Submit material through coffer__write").
 * Counts, the inbox and the timeline all move, so the whole subtree is
 * invalidated. No toast either way: the dialog says where the item went and
 * renders a refusal beside its fields.
 */
export function useSubmitMaterial() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: MaterialIn) => submitMaterial(input),
    onSuccess: () => void qc.invalidateQueries({ queryKey: knowledgeKey }),
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
 * the two happened. Which one it was is the caller's toast to report, and a
 * refusal (an unsupported type, a file too large) is rendered in the upload
 * dialog, where the file still is — so no `onError` toast here.
 */
export function useUploadKnowledgeFile() {
  const qc = useQueryClient();
  return useMutation({
    // `collection` is the collection's NAME here, not its uid: an upload lands
    // material in a directory, and the directory is named after the collection.
    mutationFn: (vars: { collection: string; file: File }) => uploadFile(vars),
    onSuccess: () => void qc.invalidateQueries({ queryKey: knowledgeKey }),
  });
}
