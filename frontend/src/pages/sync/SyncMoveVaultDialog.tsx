// frontend/src/pages/sync/SyncMoveVaultDialog.tsx — "Move the vault out of
// iCloud Drive" (board 6.4.19), opened from the cloud-folder problem card.
//
// Coffer pauses rounds and agent writes, moves the folder, checks the git
// repository and resumes (`POST /sync/vault/move`). The target must not sit
// inside iCloud Drive, Dropbox or Syncthing either — the daemon refuses such a
// target and says why. The old folder is left empty for the person to delete.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";

import { FolderPickerField } from "@/components/FolderPickerField";
import { Button } from "@/components/ui/button";
import { DialogErrorBanner } from "@/components/ui/confirm-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { SyncStatus } from "@/lib/api/sync";
import { useMoveVault } from "@/lib/hooks/useSync";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  status: SyncStatus;
}

export function SyncMoveVaultDialog({ open, onOpenChange, status }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const move = useMoveVault();
  const from = status.vault_real_path ?? status.vault_path;
  const [target, setTarget] = useState<string | null>(null);
  // Until the person picks another folder, the daemon's suggestion stands.
  const to = target ?? status.default_vault_path ?? "";
  const tool = status.synchroniser ?? t("sync.problem.cloud_folder.someTool");

  const close = () => {
    if (move.isPending) return;
    onOpenChange(false);
    move.reset();
    setTarget(null);
  };

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
      <DialogContent className="max-w-[480px]">
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (!to.trim() || move.isPending) return;
            move.mutate(to.trim(), {
              onSuccess: (result) => {
                toast.success(t("sync.problem.cloud_folder.moved", { to: result.to }));
                close();
              },
            });
          }}
        >
          <DialogHeader>
            <DialogTitle>{t("sync.moveVault.title", { tool })}</DialogTitle>
            <DialogDescription>{t("sync.moveVault.lead")}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-1.5">
            <Label>{t("sync.moveVault.from")}</Label>
            <p
              className="truncate rounded-md border border-border bg-surface-raised px-2.5 py-[7px] font-mono text-xs text-text"
              title={from}
              data-testid="move-vault-from"
            >
              {from}
            </p>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="move-vault-to">{t("sync.moveVault.to")}</Label>
            <FolderPickerField
              inputId="move-vault-to"
              value={to}
              onChange={(path) => setTarget(path ?? "")}
              typeable
            />
            <p className="text-xs text-text-muted">{t("sync.moveVault.rule")}</p>
          </div>
          <p className="flex items-start gap-2 text-xs text-text-muted">
            <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            {t("sync.moveVault.oldFolder")}
          </p>
          {move.error ? (
            <DialogErrorBanner
              title={t("sync.moveVault.failed")}
              message={translateApiError(t, move.error)}
            />
          ) : null}
          <DialogFooter>
            <Button type="button" variant="ghost" disabled={move.isPending} onClick={close}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={!to.trim()} loading={move.isPending}>
              {t("sync.moveVault.confirm")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
