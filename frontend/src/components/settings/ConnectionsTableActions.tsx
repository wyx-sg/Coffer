// frontend/src/components/settings/ConnectionsTableActions.tsx
// Row + bulk actions for ConnectionsTable, kept out of that file so it stays
// within its size budget (mirrors SkillsTableActions). Per row: the connection's
// own enable/disable Switch (there is still NO per-row "activate" — projection
// is per-agent and lives on the Agent detail → Overview tab) + Delete (the
// styled confirm is hoisted to the table). Bulk: enable / disable / delete over
// the selection, fanned out with useBulkMutate so one failure never aborts the
// rest.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Power, PowerOff, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { providersApi, type Provider } from "@/lib/api/providers";
import { resourcesApi } from "@/lib/api/resources";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";
import { useSetProviderEnabled } from "@/lib/hooks/useProviders";

const DESTRUCTIVE =
  "text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive";

/** Per-row enable/disable toggle; stops propagation so it doesn't trigger the
 *  row's navigate-to-detail click. */
export function ConnectionStatusCell({ provider }: { provider: Provider }) {
  const { t } = useTranslation();
  const { enable, disable } = useSetProviderEnabled();

  return (
    <Switch
      checked={provider.enabled}
      onClick={(e) => e.stopPropagation()}
      onCheckedChange={(checked) => (checked ? enable : disable).mutate(provider.name)}
      disabled={enable.isPending || disable.isPending}
      aria-label={`${t("resources.cols.status")}: ${provider.name}`}
    />
  );
}

/** The per-row action: Delete (confirm). The dialog it opens is rendered at the
 *  table level so closing it can't fall through to the row's navigation. */
export function ConnectionRowActions({
  provider,
  onDelete,
  deleteDisabled,
}: {
  provider: Provider;
  onDelete: () => void;
  deleteDisabled: boolean;
}) {
  const { t } = useTranslation();

  return (
    <div className="flex items-center justify-end gap-2">
      <Button
        size="sm"
        variant="ghost"
        className="text-muted-foreground hover:text-destructive"
        aria-label={`${t("common.delete")}: ${provider.name}`}
        disabled={deleteDisabled}
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
      >
        <Trash2 className="mr-1.5 size-3.5" /> {t("common.delete")}
      </Button>
    </div>
  );
}

/** Selection-bar actions: Enable / Disable / Delete the selected connections. */
export function ConnectionsBulkActions({
  providers,
  onDone,
}: {
  providers: Provider[];
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const bulk = useBulkMutate({ invalidate: [["providers"]] });
  const [confirmOpen, setConfirmOpen] = useState(false);

  const setEnabled = async (enabled: boolean) => {
    const call = enabled ? resourcesApi.enable : resourcesApi.disable;
    await bulk.run(providers, (p) => call("provider", p.name));
    onDone();
  };

  const deleteSelected = async () => {
    await bulk.run(providers, (p) => providersApi.remove(p.name));
    setConfirmOpen(false);
    onDone();
  };

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        disabled={bulk.isPending}
        onClick={() => void setEnabled(true)}
      >
        <Power className="mr-1.5 size-3.5" /> {t("common.bulk.enable")}
      </Button>
      <Button
        size="sm"
        variant="outline"
        disabled={bulk.isPending}
        onClick={() => void setEnabled(false)}
      >
        <PowerOff className="mr-1.5 size-3.5" /> {t("common.bulk.disable")}
      </Button>
      <Button
        size="sm"
        variant="outline"
        className={DESTRUCTIVE}
        disabled={bulk.isPending}
        onClick={() => setConfirmOpen(true)}
      >
        <Trash2 className="mr-1.5 size-3.5" /> {t("common.bulk.delete")}
      </Button>

      <Dialog open={confirmOpen} onOpenChange={(o) => !o && setConfirmOpen(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("settings.connections.deleteTitle")}</DialogTitle>
            <DialogDescription>
              {t("settings.connections.bulkDeleteConfirm", { count: providers.length })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={bulk.isPending}
              onClick={() => void deleteSelected()}
            >
              {bulk.isPending ? t("common.deleting") : t("common.bulk.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
