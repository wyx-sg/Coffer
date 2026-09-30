// frontend/src/pages/sync/SyncMachineDialogs.tsx
//
// The Machines tab's two dialogs. Rename (6.5.29) changes only this Mac's
// name in the list — nothing keys on the label, and other Macs see it after
// their next round. Retire (6.5.21) removes another Mac's descriptor from the
// registry and nothing else: its rounds stay in history, nothing on that Mac
// or in the repository changes, and if it syncs again it reappears. Both
// close only on success, so a refusal stays up with its reason.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog, DialogErrorBanner } from "@/components/ui/confirm-dialog";
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
import { useRenameSelf, useRetireMachine } from "@/lib/hooks/useMachines";
import { lastSeenLabel } from "./syncMachineTimes";

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

export function RetireMachineDialog({ machine, now, onClose }: Props & { now: Date }) {
  const { t, i18n } = useTranslation();
  const retire = useRetireMachine();

  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => {
        if (open) return;
        retire.reset();
        onClose();
      }}
      title={t("sync.machines.retireTitle", { name: machine.name })}
      description={t("sync.machines.retireSeen", {
        when: lastSeenLabel(machine.last_round_at, now, t, i18n.language),
        version: machine.coffer_version,
      })}
      confirmLabel={t("sync.machines.retire")}
      pending={retire.isPending}
      error={retire.error}
      onConfirm={() => retire.mutate(machine.machine_id, { onSuccess: onClose })}
    >
      <div className="flex items-start gap-3 rounded-lg border border-border-subtle px-3.5 py-3">
        <Info className="mt-0.5 size-4 shrink-0 text-text-muted" aria-hidden />
        <div className="flex flex-col gap-1">
          <p className="text-sm font-label text-text">{t("sync.machines.retireSafeTitle")}</p>
          <p className="text-xs text-text-muted">{t("sync.machines.retireSafe")}</p>
        </div>
      </div>
    </ConfirmDialog>
  );
}
