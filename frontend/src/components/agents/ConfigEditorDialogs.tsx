// frontend/src/components/agents/ConfigEditorDialogs.tsx — spec 004.
// The two modal dialogs of the agent config editor, extracted from
// AgentConfigFilesEditor to keep that file inside the component size cap:
//   - the new-file dialog for a directory-backed config key, and
//   - the delete-child confirm dialog.
// All state (open targets, input value, mutation objects) stays in the
// parent; these components only render and call back.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { translateApiError } from "@/lib/api/errors";

export interface NewChildFileDialogProps {
  /** Directory key the new file is created under; null = dialog closed. */
  dirKey: string | null;
  /** Resolved path of that directory (shown as the dialog description). */
  dirPath: string | null;
  name: string;
  invalid: boolean;
  error: unknown;
  pending: boolean;
  onNameChange: (next: string) => void;
  onSubmit: () => void;
  onClose: () => void;
}

export function NewChildFileDialog({
  dirKey,
  dirPath,
  name,
  invalid,
  error,
  pending,
  onNameChange,
  onSubmit,
  onClose,
}: NewChildFileDialogProps) {
  const { t } = useTranslation();
  return (
    <Dialog
      open={dirKey !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("agents.config.newFile")}</DialogTitle>
          <DialogDescription className="font-mono text-xs">
            {dirPath ?? dirKey}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1">
          <Input
            value={name}
            onChange={(e) => onNameChange(e.target.value)}
            placeholder={t("agents.config.newFilePlaceholder")}
            aria-label={t("agents.config.newFile")}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                onSubmit();
              }
            }}
          />
          {invalid ? (
            <p role="alert" className="text-xs text-destructive">
              {t("agents.config.invalidChildName")}
            </p>
          ) : error ? (
            <p role="alert" className="text-xs text-destructive">
              {translateApiError(t, error)}
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={onSubmit} disabled={pending}>
            {t("agents.config.newFile")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export interface DeleteChildDialogProps {
  /** Child being deleted; null = dialog closed. */
  target: { key: string; relpath: string } | null;
  pending: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

export function DeleteChildDialog({
  target,
  pending,
  onConfirm,
  onClose,
}: DeleteChildDialogProps) {
  const { t } = useTranslation();
  return (
    <Dialog
      open={target !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t("agents.config.deleteChild")}: {target?.relpath}
          </DialogTitle>
          <DialogDescription>
            {t("agents.config.deleteChildConfirm", { relpath: target?.relpath })}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button variant="destructive" disabled={pending} onClick={onConfirm}>
            {t("agents.config.deleteChild")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
