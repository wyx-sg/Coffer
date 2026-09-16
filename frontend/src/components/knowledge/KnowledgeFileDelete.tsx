// frontend/src/components/knowledge/KnowledgeFileDelete.tsx
//
// Delete the ONE file being previewed on a collection's detail page.
//
// Deleting the collection is the library page's action, on the Resource; this
// is the file-sized one, which the UI did not have at all — a collection could
// be removed whole and not a single document out of it. The previewed file is
// the anchor because it is the only file the page can name for certain: it is
// the one on screen.
//
// A knowledge file is the only copy — no index behind it, no soft delete — so
// the confirmation spells the path out rather than describing it, and the
// dialog closes only on success so a refusal is read where it happened
// (.agents/frontend.md §5).
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useDeleteKnowledgeFile } from "@/lib/hooks/useKnowledge";

interface Props {
  /** The collection-relative path of the file on screen. */
  path: string;
  /** Called once the daemon has removed it — the page leaves the pane rather
   *  than keep previewing a path that is now a 404. */
  onDeleted: () => void;
}

export function KnowledgeFileDelete({ path, onDeleted }: Props) {
  const { t } = useTranslation();
  const removeFile = useDeleteKnowledgeFile();
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="text-destructive hover:text-destructive"
        onClick={() => setOpen(true)}
        disabled={removeFile.isPending}
      >
        <Trash2 className="mr-1.5 size-3.5" aria-hidden />
        {t("knowledge.detail.deleteFile")}
      </Button>

      <ConfirmDialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          // A refusal read once should not greet the next attempt.
          if (!next) removeFile.reset();
        }}
        title={t("knowledge.detail.deleteFileTitle")}
        description={t("knowledge.detail.deleteFileConfirm", { path })}
        confirmLabel={removeFile.isPending ? t("common.deleting") : t("common.delete")}
        pending={removeFile.isPending}
        error={removeFile.error}
        onConfirm={() =>
          removeFile.mutate(path, {
            onSuccess: () => {
              setOpen(false);
              onDeleted();
            },
          })
        }
      />
    </>
  );
}
