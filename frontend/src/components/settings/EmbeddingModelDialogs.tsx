// components/settings/EmbeddingModelDialogs.tsx
// The add/edit-model dialog plus the "changing the model re-embeds everything"
// confirmation for the global Embedding settings. Split out of EmbeddingSettings
// to keep that page within its size budget; purely presentational — all state
// (open flags, the pending model values) lives in the parent and is passed in.
import { useTranslation } from "react-i18next";

import {
  EmbeddingModelDialog,
  type EmbeddingModelInitial,
  type EmbeddingModelValues,
} from "@/components/settings/EmbeddingModelDialog";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

interface Props {
  open: boolean;
  onClose: () => void;
  hasModel: boolean;
  initial: EmbeddingModelInitial;
  pending: boolean;
  onSubmit: (values: EmbeddingModelValues) => void;
  /** Pending model values held behind the change-model confirmation, or null. */
  confirm: EmbeddingModelValues | null;
  onConfirmClose: () => void;
  onConfirmAccept: (values: EmbeddingModelValues) => void;
}

export function EmbeddingModelDialogs({
  open,
  onClose,
  hasModel,
  initial,
  pending,
  onSubmit,
  confirm,
  onConfirmClose,
  onConfirmAccept,
}: Props) {
  const { t } = useTranslation();
  return (
    <>
      <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {hasModel ? t("settings.embedding.editTitle") : t("settings.embedding.addTitle")}
            </DialogTitle>
          </DialogHeader>
          <EmbeddingModelDialog
            initial={initial}
            pending={pending}
            onSubmit={onSubmit}
            onCancel={onClose}
          />
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(o) => !o && onConfirmClose()}
        title={t("settings.embedding.changeModelTitle")}
        description={t("settings.embedding.changeModelConfirm")}
        confirmLabel={t("settings.embedding.changeModelConfirmLabel")}
        variant="default"
        pending={pending}
        onConfirm={() => {
          if (confirm) onConfirmAccept(confirm);
        }}
      />
    </>
  );
}
