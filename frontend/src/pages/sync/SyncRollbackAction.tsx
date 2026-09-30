// frontend/src/pages/sync/SyncRollbackAction.tsx
//
// "Roll back to before the 14:32 round?" (6.5.10), opened from a round's row
// or from its detail drawer.
//
// The dialog says what will come back before anything does: the daemon is
// asked for the plan (`GET /sync/runs/{id}/rollback-plan`) the moment the
// dialog opens — the snapshot the round took, each file it would put back,
// and the files edited since, which are kept as they are. Rolling back is a
// new commit here that the next round pushes, so the other Macs follow and
// nothing another machine did after is lost. Once it lands, the round's own
// toast says so and the Status banner reads "Rolled back" (6.5.11).
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { SyncChange, SyncRound } from "@/lib/api/sync";
import { useRollbackPlan, useRollbackRound } from "@/lib/hooks/useSync";
import { changeLine } from "./syncRoundStatus";
import { clock, clockSeconds } from "./syncTime";

/** Past this, lines are summarised: a dialog that scrolls past its own confirm
 *  button answers "what is about to happen" worse than a count does. */
const MAX_PATHS = 20;

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex h-5 items-center rounded-sm bg-chip px-1.5 text-2xs font-label text-text-muted">
      {children}
    </span>
  );
}

/** What each reversed file goes back to, from the round's side of it. */
function reverseNote(t: TFunction, change: SyncChange, at: string | null) {
  // The rollback REMOVES a file the round added, and RESTORES one it removed.
  if (change.status === "removed") return t("sync.rollback.wasAdded");
  if (change.status === "added") return t("sync.rollback.wasRemoved");
  return at ? t("sync.rollback.backTo", { time: at }) : t("sync.rollback.backToSnapshot");
}

interface Props {
  /** The round to roll back; null while the dialog is closed. */
  run: (SyncRound & { id: number }) | null;
  onClose: () => void;
}

export function SyncRollbackDialog({ run, onClose }: Props) {
  const { t } = useTranslation();
  const open = run !== null;
  const plan = useRollbackPlan(run?.id ?? null, open);
  const rollback = useRollbackRound();
  const reverses = plan.data?.reverses ?? [];
  const shown = reverses.slice(0, MAX_PATHS);
  const snapAt = plan.data?.snapshot_time ?? null;
  const when = run ? clock(run.finished_at) : "";

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        if (next) return;
        onClose();
        // A refusal read once should not greet the next attempt.
        rollback.reset();
      }}
      title={t("sync.rollback.title", { time: when })}
      description={t("sync.rollback.description")}
      confirmLabel={t("sync.rollback.confirm")}
      pendingLabel={t("sync.rollback.rollingBack")}
      variant="default"
      pending={rollback.isPending || plan.isLoading}
      error={rollback.error ?? plan.error}
      onConfirm={() => {
        if (!run) return;
        // Closes only on success, so a refusal stays up with its reason.
        rollback.mutate(run.id, { onSuccess: onClose });
      }}
    >
      {plan.isLoading ? (
        <p className="text-sm text-text-muted">{t("common.loading")}</p>
      ) : plan.data && run ? (
        <div className="space-y-3" data-testid="sync-rollback-plan">
          <div className="flex flex-wrap gap-1.5">
            <Chip>{t("sync.rollback.pulled", { count: run.pulled_files })}</Chip>
            <Chip>{t("sync.rollback.pushed", { count: run.pushed_files })}</Chip>
            <Chip>
              <span className="font-mono">
                {plan.data.snapshot}
                {snapAt ? ` · ${clockSeconds(snapAt)}` : ""}
              </span>
            </Chip>
          </div>
          {shown.length > 0 ? (
            <div className="space-y-1.5">
              <p className="text-2xs font-semibold uppercase tracking-wide text-text-subtle">
                {t("sync.rollback.reverses")}
              </p>
              <ul
                className="space-y-1 rounded-lg bg-surface-sunken px-3 py-2.5"
                data-testid="sync-rollback-paths"
              >
                {shown.map((change) => (
                  <li key={change.path} className="flex items-center gap-3 text-xs">
                    <span className="min-w-0 flex-1 truncate font-mono text-text">
                      {changeLine(change)}
                    </span>
                    <span className="shrink-0 text-text-subtle">
                      {reverseNote(t, change, snapAt ? clock(snapAt) : null)}
                    </span>
                  </li>
                ))}
              </ul>
              {reverses.length > shown.length ? (
                <p className="text-xs text-text-muted">
                  {t("sync.rollback.morePaths", { count: reverses.length - shown.length })}
                </p>
              ) : null}
            </div>
          ) : null}
          <div className="flex gap-3 rounded-lg border border-border p-3">
            <span
              aria-hidden
              className="inline-flex size-7 shrink-0 items-center justify-center rounded-md border border-border-subtle text-text-muted"
            >
              <RefreshCw className="size-3.5" />
            </span>
            <div className="space-y-0.5">
              <p className="text-sm font-label text-text">{t("sync.rollback.followTitle")}</p>
              <p className="text-xs text-text-muted">
                {t("sync.rollback.followBody", { time: when })}
              </p>
            </div>
          </div>
          {plan.data.kept.length > 0 ? (
            <div className="space-y-1" data-testid="sync-rollback-kept">
              <p className="text-xs text-text-muted">{t("sync.rollback.kept")}</p>
              <ul className="space-y-0.5">
                {plan.data.kept.slice(0, MAX_PATHS).map((path) => (
                  <li key={path} className="font-mono text-xs text-text">
                    {path}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </ConfirmDialog>
  );
}
