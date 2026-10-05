// frontend/src/components/knowledge/KnowledgeDeleteCollection.tsx
//
// Delete collection… from a collection page's ⋯ menu (boards 5.1.10, 5.1.14;
// spec knowledge "Delete a document at once, a collection after asking, and
// offer Undo"). It asks first — a confirmation naming the collection and how
// many documents it holds, with no typed name — because once the toast closes a
// collection cannot be brought back from the page (git has its files, not its
// registration). The dialog closes only on success and is pending while the
// delete runs. Then the page goes to Knowledge and the toast carries Undo,
// which restores the delete from the changes feed. A collection is one
// `knowledge` Resource, so it goes through the kind-agnostic resource delete
// like every other kind.
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { CollectionOut } from "@/lib/api/knowledge";
import { useDeleteResource } from "@/lib/hooks/useResourceMutations";
import { undoDelete } from "@/lib/knowledge/deleteUndo";
import { KNOWLEDGE_ROOT } from "@/lib/knowledge/routes";

interface Props {
  collection: CollectionOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function KnowledgeDeleteCollection({ collection, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const navigate = useNavigate();
  const del = useDeleteResource();

  const confirm = () =>
    del.mutateAsync({ kind: "knowledge", uid: collection.uid }).then(() => {
      navigate(KNOWLEDGE_ROOT);
      toast.success(t("knowledge.deleteCollection.deleted", { name: collection.name }), {
        undo: () =>
          void undoDelete({ collection: collection.name }).catch((error: unknown) =>
            toast.error(t("knowledge.deleteCollection.undoFailed", { name: collection.name }), {
              details: translateApiError(t, error),
            }),
          ),
      });
    });

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("knowledge.deleteCollection.title", { name: collection.name })}
      description={t("knowledge.deleteCollection.body", { count: collection.document_count })}
      confirmLabel={t("knowledge.deleteCollection.confirm")}
      pendingLabel={t("knowledge.deleteCollection.pending")}
      errorTitle={t("knowledge.deleteCollection.failed", { name: collection.name })}
      error={del.error}
      onConfirm={confirm}
    />
  );
}
