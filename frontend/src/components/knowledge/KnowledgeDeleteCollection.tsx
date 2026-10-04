// frontend/src/components/knowledge/KnowledgeDeleteCollection.tsx
//
// Delete collection… from a collection page's ⋯ menu (boards 5.1.10, 5.1.14).
// It runs at once, with no dialog and no typed name: the delete is one change
// in the vault's history, so the toast carries Undo, which restores it from
// there (layout principle 14, "confirm or undo"; spec knowledge "Restore a
// deleted collection or document from Recent changes"). A collection is one
// `knowledge` Resource, so it goes through the kind-agnostic resource delete
// like every other kind. Once it has landed the page goes to Recent changes,
// where the delete also stays restorable.
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { CollectionOut } from "@/lib/api/knowledge";
import { useDeleteResource } from "@/lib/hooks/useResourceMutations";
import { undoDelete } from "@/lib/knowledge/deleteUndo";
import { KNOWLEDGE_ROOT } from "@/lib/knowledge/routes";

/** The action behind the menu item: delete `collection`, then toast with Undo. */
export function useDeleteCollection(collection: CollectionOut): () => void {
  const { t } = useTranslation();
  const { toast } = useToast();
  const navigate = useNavigate();
  const del = useDeleteResource();

  return () =>
    del.mutate(
      { kind: "knowledge", uid: collection.uid },
      {
        onSuccess: () => {
          navigate(KNOWLEDGE_ROOT);
          toast.success(t("knowledge.deleteCollection.deleted", { name: collection.name }), {
            undo: () =>
              void undoDelete({ collection: collection.name }).catch((error: unknown) =>
                toast.error(t("knowledge.deleteCollection.undoFailed", { name: collection.name }), {
                  details: translateApiError(t, error),
                }),
              ),
          });
        },
      },
    );
}
