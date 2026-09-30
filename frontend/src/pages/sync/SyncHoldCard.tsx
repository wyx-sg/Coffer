// frontend/src/pages/sync/SyncHoldCard.tsx
//
// A round the deletion breaker held (spec vault-sync): it would have deleted
// more of an area than the breaker lets through without a person. The round is
// waiting, and there are exactly two answers — delete the files, or restore
// them — each naming how many it touches.
//
// Grouped by folder with each folder's share, because "12 files" means one
// thing when it is 12 of 400 and another when it is every file the folder had.
// Deleting asks again; restoring does not, because it destroys nothing.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2, Undo2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { SyncHold } from "@/lib/api/sync";
import { useConfirmHold, useRestoreHold } from "@/lib/hooks/useSyncStop";

/** Past this, a folder's paths are summarised rather than listed. */
const MAX_PATHS = 10;

function share(count: number, total: number): number {
  return total > 0 ? Math.round((count / total) * 100) : 100;
}

export function SyncHoldCard({ hold }: { hold: SyncHold }) {
  const { t } = useTranslation();
  const confirm = useConfirmHold();
  const restore = useRestoreHold();
  const [confirming, setConfirming] = useState(false);
  const count = hold.paths.length;
  const busy = confirm.isPending || restore.isPending;
  const who =
    hold.direction === "outgoing"
      ? t("sync.hold.thisMac")
      : hold.machines.join(", ") || t("sync.hold.anotherMachine");

  return (
    <Card data-testid="sync-hold">
      <CardHeader>
        <CardTitle>{t("sync.hold.title", { who, count })}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{t(`sync.hold.body.${hold.direction}`)}</p>
        <ul className="space-y-3">
          {hold.groups.map((group) => (
            <li key={group.folder} className="space-y-1">
              <p className="text-sm font-medium">
                <span className="font-mono">{group.folder}</span>{" "}
                <span className="text-muted-foreground">
                  {t("sync.hold.share", {
                    count: group.paths.length,
                    percent: share(group.paths.length, group.total),
                  })}
                </span>
              </p>
              <ul className="space-y-0.5 font-mono text-xs text-muted-foreground">
                {group.paths.slice(0, MAX_PATHS).map((path) => (
                  <li key={path}>{path}</li>
                ))}
                {group.paths.length > MAX_PATHS ? (
                  <li>{t("sync.hold.more", { count: group.paths.length - MAX_PATHS })}</li>
                ) : null}
              </ul>
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap gap-3">
          <Button
            type="button"
            variant="destructive"
            disabled={busy}
            onClick={() => setConfirming(true)}
          >
            <Trash2 className="size-4" aria-hidden />
            {t("sync.hold.delete", { count })}
          </Button>
          <Button type="button" variant="outline" disabled={busy} onClick={() => restore.mutate()}>
            <Undo2 className="size-4" aria-hidden />
            {restore.isPending ? t("sync.hold.restoring") : t("sync.hold.restore", { count })}
          </Button>
        </div>
      </CardContent>
      <ConfirmDialog
        open={confirming}
        onOpenChange={(next) => {
          setConfirming(next);
          if (!next) confirm.reset();
        }}
        title={t("sync.hold.confirmTitle", { count })}
        description={t("sync.hold.confirmBody", { count })}
        confirmLabel={
          confirm.isPending ? t("sync.hold.deleting") : t("sync.hold.delete", { count })
        }
        pending={busy}
        error={confirm.error}
        onConfirm={() => confirm.mutate(undefined, { onSuccess: () => setConfirming(false) })}
      />
    </Card>
  );
}
