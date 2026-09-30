// frontend/src/components/knowledge/KnowledgeDeleteDocument.tsx
//
// Delete document… — any document, whoever wrote it (spec knowledge "Let only
// a person delete a document"). The confirmation names the exact file on disk
// before anything runs; a refusal stays in the dialog, and the pane leaves the
// document only once it is gone. The deletion is itself a version, so the
// document can come back from its History.
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useDeleteKnowledgeFile } from "@/lib/hooks/useKnowledge";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Knowledge-root-relative path — what the delete is addressed to. */
  path: string;
  /** The absolute path on disk — what the confirmation names. */
  filePath: string;
  onDeleted: () => void;
}

export function KnowledgeDeleteDocument({ open, onOpenChange, path, filePath, onDeleted }: Props) {
  const { t } = useTranslation();
  const removeFile = useDeleteKnowledgeFile();
  const name = path.split("/").pop() ?? path;

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) removeFile.reset();
      }}
      title={t("knowledge.deleteDocument.title", { name })}
      description={t("knowledge.deleteDocument.body")}
      confirmLabel={
        removeFile.isPending ? t("common.deleting") : t("knowledge.deleteDocument.confirm")
      }
      pending={removeFile.isPending}
      error={removeFile.error}
      onConfirm={() =>
        removeFile.mutate(path, {
          onSuccess: () => {
            onOpenChange(false);
            onDeleted();
          },
        })
      }
    >
      <p className="break-all rounded-md bg-surface-sunken px-3 py-2 font-mono text-xs">
        {filePath}
      </p>
      <p className="text-sm text-text-muted">{t("knowledge.deleteDocument.afterwards")}</p>
    </ConfirmDialog>
  );
}
