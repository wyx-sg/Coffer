// frontend/src/pages/sync/SyncMachineDialogs.tsx
//
// The Machines tab's Rename dialog (6.4.25): changes only this Mac's name in
// the list — nothing keys on the label, and other Macs see it after their next
// round. It closes only on success, so a refusal stays up with its reason.
// (Retire has no dialog: it runs at once with an Undo toast.)
import { useState } from "react";
import { useTranslation } from "react-i18next";

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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { translateApiError } from "@/lib/api/errors";
import type { Machine } from "@/lib/api/sync";
import { useRenameSelf } from "@/lib/hooks/useMachines";

interface Props {
  machine: Machine;
  onClose: () => void;
}

export function RenameMachineDialog({ machine, onClose }: Props) {
  const { t } = useTranslation();
  const rename = useRenameSelf();
  const [name, setName] = useState(machine.name);
  const next = name.trim();
  const canSave = next.length > 0 && next !== machine.name && !rename.isPending;

  return (
    <Dialog open onOpenChange={(open) => !open && !rename.isPending && onClose()}>
      <DialogContent className="max-w-[420px]">
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (canSave) rename.mutate(next, { onSuccess: onClose });
          }}
        >
          <DialogHeader>
            <DialogTitle>{t("sync.machines.renameTitle", { name: machine.name })}</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="sync-machine-name">{t("sync.machines.nameLabel")}</Label>
            <Input
              id="sync-machine-name"
              value={name}
              autoFocus
              disabled={rename.isPending}
              onChange={(e) => setName(e.target.value)}
            />
            <DialogDescription className="text-xs">
              {t("sync.machines.renameHint")}
            </DialogDescription>
          </div>
          {rename.error ? (
            <DialogErrorBanner
              title={t("common.actionFailed")}
              message={translateApiError(t, rename.error)}
            />
          ) : null}
          <DialogFooter>
            <Button type="button" variant="ghost" disabled={rename.isPending} onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={!canSave} loading={rename.isPending}>
              {t("sync.machines.rename")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
