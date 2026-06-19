// frontend/src/lib/hooks/useKnowledge.ts
//
// TanStack Query bindings for the unified 知识 surface (specs 006/007, ADR-030).
// It composes the two existing faces — memory stores (notes) and knowledge-base
// documents — into one scope-keyed view. Query keys are hierarchical under the
// `knowledge` noun so a scope's subtree invalidates as a group (frontend.md §3).
//
// Reads stay per-face (the daemon has no merged endpoint); this hook fans out
// the per-KB document lists for the selected scope and merges them with the
// scope's facts in `lib/api/knowledge.ts`'s pure mappers.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import {
  addFact,
  deleteFact,
  listFacts,
  listMemoryStores,
  type FactInput,
} from "@/kinds/memory/api";
import {
  deleteDocument,
  ingestDocument,
  listDocuments,
  listKnowledgeBases,
  restoreDocument,
  type KnowledgeBaseOut,
} from "@/kinds/knowledge_base/api";
import {
  documentFromDoc,
  noteFromFact,
  scopesFromStores,
  type KnowledgeItem,
  type KnowledgeScope,
} from "@/lib/api/knowledge";

export const knowledgeKey = ["knowledge"] as const;
export const scopesKey = [...knowledgeKey, "scopes"] as const;
export const kbsKey = [...knowledgeKey, "kbs"] as const;
export const scopeItemsKey = (scopeId: string) => [...knowledgeKey, "scope", scopeId] as const;
export const trashKey = (scopeId: string) => [...knowledgeKey, "trash", scopeId] as const;

const DOC_PAGE = 200;
const FACT_PAGE = 200;

/** The scope axis, derived from the memory stores (global + per project). */
export function useKnowledgeScopes() {
  return useQuery({
    queryKey: scopesKey,
    queryFn: async (): Promise<KnowledgeScope[]> =>
      scopesFromStores((await listMemoryStores()).memory_stores),
  });
}

/** The knowledge bases (the upload targets + the doc corpora to scan per scope). */
export function useKnowledgeBases() {
  return useQuery({ queryKey: kbsKey, queryFn: listKnowledgeBases });
}

/**
 * The unified, intermixed notes + documents for one scope. Notes come from the
 * scope's memory store; documents from every KB filtered to this scope's
 * project_id. Disabled until the scope and the KB list are known.
 */
export function useKnowledgeItems(scope: KnowledgeScope | undefined, kbs: KnowledgeBaseOut[]) {
  return useQuery({
    queryKey: scopeItemsKey(scope?.id ?? "none"),
    enabled: Boolean(scope),
    queryFn: async (): Promise<KnowledgeItem[]> => {
      if (!scope) return [];
      const notes: KnowledgeItem[] = [];
      if (scope.memoryStoreName) {
        const facts = await listFacts(scope.memoryStoreName, FACT_PAGE, 0);
        for (const f of facts.facts) notes.push(noteFromFact(scope.memoryStoreName, scope.id, f));
      }
      const docLists = await Promise.all(
        kbs.map((kb) => listDocuments(kb.name, { limit: DOC_PAGE, projectId: scope.id })),
      );
      const docs: KnowledgeItem[] = [];
      kbs.forEach((kb, i) => {
        for (const d of docLists[i].documents) docs.push(documentFromDoc(kb.name, d));
      });
      return [...notes, ...docs].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
    },
  });
}

/** The trash for one scope: soft-deleted documents across every KB. */
export function useKnowledgeTrash(scope: KnowledgeScope | undefined, kbs: KnowledgeBaseOut[]) {
  return useQuery({
    queryKey: trashKey(scope?.id ?? "none"),
    enabled: Boolean(scope),
    queryFn: async (): Promise<KnowledgeItem[]> => {
      if (!scope) return [];
      const lists = await Promise.all(
        kbs.map((kb) =>
          listDocuments(kb.name, { limit: DOC_PAGE, projectId: scope.id, deleted: true }),
        ),
      );
      const out: KnowledgeItem[] = [];
      kbs.forEach((kb, i) => {
        for (const d of lists[i].documents) out.push(documentFromDoc(kb.name, d));
      });
      return out.sort((a, b) => (b.deletedAt ?? "").localeCompare(a.deletedAt ?? ""));
    },
  });
}

/** Mutations for the unified surface, all invalidating the scope subtree. */
export function useKnowledgeMutations(scopeId: string | undefined) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: knowledgeKey });
  };
  // frontend.md §5: a failed mutation surfaces a toast by default, so a failed
  // note add / delete / document delete-or-purge / restore is never silent.
  const onError = (error: unknown) => toast.error(translateApiError(t, error));

  const addNote = useMutation({
    mutationFn: (vars: { store: string; input: FactInput }) => addFact(vars.store, vars.input),
    onSuccess: invalidate,
    onError,
  });

  const uploadDocument = useMutation({
    mutationFn: (vars: { kb: string; file: File; projectId: string; replace?: boolean }) =>
      ingestDocument(vars.kb, vars.file, { projectId: vars.projectId, replace: vars.replace }),
    onSuccess: invalidate,
    onError,
  });

  const removeNote = useMutation({
    mutationFn: (vars: { store: string; factId: string }) => deleteFact(vars.store, vars.factId),
    onSuccess: invalidate,
    onError,
  });

  // Delete a LIVE document → soft-delete (trash). Delete a TRASHED document →
  // purge. The same endpoint; the server decides by the row's deleted_at.
  const deleteOrPurgeDocument = useMutation({
    mutationFn: (vars: { kb: string; documentId: string }) =>
      deleteDocument(vars.kb, vars.documentId),
    onSuccess: invalidate,
    onError,
  });

  const restore = useMutation({
    mutationFn: (vars: { kb: string; documentId: string }) =>
      restoreDocument(vars.kb, vars.documentId),
    onSuccess: invalidate,
    onError,
  });

  return { scopeId, addNote, uploadDocument, removeNote, deleteOrPurgeDocument, restore };
}
