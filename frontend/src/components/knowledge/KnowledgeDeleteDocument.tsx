// frontend/src/components/knowledge/KnowledgeDeleteDocument.tsx
//
// Delete document (board 5.1.02; spec knowledge "Delete a document at once, a
// collection after asking, and offer Undo"). Any document, whoever wrote it.
// There is no confirmation: the delete is one change in the vault's history, so it runs at once and the
// toast carries Undo (layout principle 14 "confirm or undo"); once the toast is
// gone, the file's versions stay in the vault's history. Afterwards the pane
// goes to the collection's page — the document is gone, so there is nothing
// left to show.
// A refusal is an error toast and the pane stays on the document.
import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import { knowledgeKey } from "@/lib/api/queryKeys";
import { useDeleteKnowledgeFile } from "@/lib/hooks/useKnowledge";
import { collectionPath } from "@/lib/knowledge/routes";
import { undoDelete } from "@/lib/knowledge/deleteUndo";

/** Returns `remove(path)` for the open collection: delete now, toast with Undo. */
export function useDeleteDocument(collectionUid: string) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { mutate: removeFile } = useDeleteKnowledgeFile();

  return useCallback(
    (path: string) => {
      const name = path.split("/").pop() ?? path;
      removeFile(path, {
        onSuccess: () => {
          toast.success(t("knowledge.deleteDocument.deletedToast", { name }), {
            undo: () =>
              void undoDelete({ document: path }).then(
                () => void qc.invalidateQueries({ queryKey: knowledgeKey }),
                (error: unknown) =>
                  toast.error(t("knowledge.deleteDocument.undoFailed", { name }), {
                    details: translateApiError(t, error),
                  }),
              ),
          });
          navigate(collectionPath(collectionUid));
        },
        onError: (error) =>
          toast.error(t("common.couldntDelete", { name }), {
            details: translateApiError(t, error),
          }),
      });
    },
    [collectionUid, navigate, qc, removeFile, t, toast],
  );
}
