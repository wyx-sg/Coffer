// frontend/src/pages/sync/SyncRollbackAction.tsx
//
// Roll one round back, from the Runs row that describes it.
//
// The dialog says what will come back before anything does: the daemon is
// asked for the plan (`GET /sync/runs/{id}/rollback-plan`) the moment the
// dialog opens — the snapshot the round took, each file it would put back, and
// the files edited since, which are kept as they are. Rolling back is a new
// commit here that the next round pushes, so nothing another machine did after
// is lost.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Undo2 } from "lucide-react";

import { TableActionButton } from "@/components/table/TableActionButton";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { SyncRound } from "@/lib/api/sync";
import { useRollbackPlan, useRollbackRound } from "@/lib/hooks/useSync";
import { formatDateTime } from "@/lib/utils";
import { SyncRoundPathList } from "./SyncRoundPathList";
import { changeLine } from "./syncRoundStatus";

/** Past this, lines are summarised: a dialog that scrolls past its own confirm
 *  button answers "what is about to happen" worse than a count does. */
const MAX_PATHS = 20;

export function SyncRollbackAction({ run }: { run: SyncRound & { id: number } }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const plan = useRollbackPlan(run.id, open);
  const rollback = useRollbackRound();
  const reverses = plan.data?.reverses ?? [];
  const shown = reverses.slice(0, MAX_PATHS);

  return (
    // The row opens its own detail on click; without this the click that
    // raises the dialog would also expand the row behind it.
    <div className="flex justify-end" onClick={(e) => e.stopPropagation()}>
      <TableActionButton
        icon={Undo2}
        label={t("sync.rollback.action")}
        onClick={() => setOpen(true)}
        disabled={rollback.isPending}
      />
      <ConfirmDialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          // A refusal read once should not greet the next attempt.
          if (!next) rollback.reset();
        }}
        title={t("sync.rollback.title")}
        description={t("sync.rollback.description", { when: formatDateTime(run.finished_at) })}
        confirmLabel={
          rollback.isPending ? t("sync.rollback.rollingBack") : t("sync.rollback.confirm")
        }
        pending={rollback.isPending || plan.isLoading}
        error={rollback.error ?? plan.error}
        onConfirm={() =>
          // Closes only on success, so a refusal stays up with its reason.
          rollback.mutate(run.id, { onSuccess: () => setOpen(false) })
        }
      >
        {plan.isLoading ? (
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : plan.data ? (
          <div className="space-y-3" data-testid="sync-rollback-plan">
            <p className="text-sm">
              {t("sync.rollback.snapshot", {
                name: plan.data.snapshot,
                when: plan.data.snapshot_time ? formatDateTime(plan.data.snapshot_time) : "—",
              })}
            </p>
            <SyncRoundPathList
              titleKey="sync.rollback.reverses"
              items={shown.map(changeLine)}
              testId="sync-rollback-paths"
            />
            {reverses.length > shown.length ? (
              <p className="text-xs text-muted-foreground">
                {t("sync.rollback.morePaths", { count: reverses.length - shown.length })}
              </p>
            ) : null}
            <p className="text-xs text-muted-foreground">{t("sync.rollback.keptNote")}</p>
            <SyncRoundPathList
              titleKey="sync.rollback.kept"
              items={plan.data.kept.slice(0, MAX_PATHS)}
              testId="sync-rollback-kept"
            />
          </div>
        ) : null}
      </ConfirmDialog>
    </div>
  );
}
