// frontend/src/kinds/mcp/McpServersTableCells.tsx
//
// Per-row cell components + the bulk-action bar for McpServersTable. These live
// here (not inline in the table) because each needs its own hooks/dialog state,
// which can't run inside a column's `cell` map, and to keep McpServersTable.tsx
// under the file-size cap.
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
import type { ResourceOut } from "@/lib/components/kindRegistry";
import {
  useEnableResource,
  useDisableResource,
  useDeleteResource,
} from "@/lib/hooks/useResourceMutations";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";
import { resourcesApi } from "@/lib/api/resources";
import { useMcpServerStatus } from "@/lib/hooks/useMcpInvocations";
import { HealthBadge } from "./HealthBadge";
import { McpServerDeleteDialog } from "./McpServerDeleteDialog";

const DESTRUCTIVE_CLS =
  "text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive";

/** Persisted health (last /test probe or most recent invocation), else "—". */
export function ServerHealthCell({ name }: { name: string }) {
  const { data: status } = useMcpServerStatus(name);
  return status ? <HealthBadge state={status} /> : <span className="text-muted-foreground">—</span>;
}

/** Enable/disable toggle; stops propagation so it doesn't trigger row click. */
export function ServerStatusCell({ resource }: { resource: ResourceOut }) {
  const { t } = useTranslation();
  const enable = useEnableResource();
  const disable = useDisableResource();
  return (
    <Switch
      checked={resource.enabled}
      onClick={(e) => e.stopPropagation()}
      onCheckedChange={(checked) =>
        (checked ? enable : disable).mutate({ kind: resource.kind, name: resource.name })
      }
      disabled={enable.isPending || disable.isPending}
      aria-label={resource.enabled ? t("common.enabled") : t("common.disabled")}
    />
  );
}

/** Delete action: icon+text button that opens a styled confirm dialog. */
export function ServerDeleteCell({ resource }: { resource: ResourceOut }) {
  const { t } = useTranslation();
  const del = useDeleteResource();
  const [open, setOpen] = useState(false);

  return (
    <div onClick={(e) => e.stopPropagation()}>
      <Button
        size="sm"
        variant="ghost"
        className="text-muted-foreground hover:text-destructive"
        aria-label={t("mcp.table.deleteAria", { name: resource.name })}
        onClick={() => setOpen(true)}
      >
        <Trash2 className="mr-1.5 size-3.5" />
        {t("common.delete")}
      </Button>
      <McpServerDeleteDialog
        name={resource.name}
        open={open}
        isPending={del.isPending}
        error={del.error}
        onOpenChange={(o) => {
          setOpen(o);
          if (!o) del.reset();
        }}
        onConfirm={() =>
          // Close only on success so a failure leaves the dialog (and error) up.
          del.mutate(
            { kind: resource.kind, name: resource.name },
            { onSuccess: () => setOpen(false) },
          )
        }
      />
    </div>
  );
}

/** Bulk enable/disable/delete over the selected rows; clears selection on done. */
export function McpServersBulkActions({
  rows,
  onDone,
}: {
  rows: ResourceOut[];
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const [confirmOpen, setConfirmOpen] = useState(false);
  // allSettled fan-out: one failed row never aborts the rest, and a single
  // summary toast reports "N done / M failed". A single ["resources"]
  // invalidation burst refreshes the table after the batch settles.
  const bulk = useBulkMutate({ invalidate: [["resources"]] });

  const runAll = async (op: (kind: string, name: string) => Promise<unknown>) => {
    await bulk.run(rows, (r) => op(r.kind, r.name));
    onDone();
  };

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        disabled={bulk.isPending}
        onClick={() => void runAll(resourcesApi.enable)}
      >
        <Power className="mr-1.5 size-3.5" />
        {t("common.bulk.enable")}
      </Button>
      <Button
        size="sm"
        variant="outline"
        disabled={bulk.isPending}
        onClick={() => void runAll(resourcesApi.disable)}
      >
        <PowerOff className="mr-1.5 size-3.5" />
        {t("common.bulk.disable")}
      </Button>
      <Button
        size="sm"
        variant="outline"
        className={DESTRUCTIVE_CLS}
        disabled={bulk.isPending}
        onClick={() => setConfirmOpen(true)}
      >
        <Trash2 className="mr-1.5 size-3.5" />
        {t("common.bulk.delete")}
      </Button>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("common.delete")}</DialogTitle>
            <DialogDescription>{t("mcp.server.deleteConfirmBody")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={bulk.isPending}
              onClick={async () => {
                // Close + clear regardless of partial failure; the summary toast
                // reports the outcome, so the bar never stays stuck silently.
                await runAll(resourcesApi.remove);
                setConfirmOpen(false);
              }}
            >
              {bulk.isPending ? t("common.deleting") : t("common.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
