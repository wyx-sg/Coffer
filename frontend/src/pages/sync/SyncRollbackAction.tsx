// frontend/src/pages/sync/SyncRollbackAction.tsx
//
// "Roll back to before the 14:32 round?" (6.4.12), opened from a round's row
// or from its detail drawer.
//
// The dialog says what will come back before anything does: the daemon is
// asked for the plan (`GET /sync/runs/{id}/rollback-plan`) the moment the
// dialog opens — the snapshot the round took, each file it would put back,
// and the files edited since, which are kept as they are. Rolling back is a
// new commit here that the next round pushes, so the other Macs follow and
// nothing another machine did after is lost. Once it lands, the round's own
// toast says so and the Status banner reads "Rolled back" (6.4.13).
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";

import { ShowAllRow } from "@/components/LongList";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useLongList } from "@/components/useLongList";
import type { SyncChange, SyncRound } from "@/lib/api/sync";
import { useRollbackPlan, useRollbackRound } from "@/lib/hooks/useSync";
import { ChangeMark, FILE_LIST, FILE_ROW } from "./SyncChangeMark";
import { clock, clockSeconds } from "./syncTime";

/** What each reversed file goes back to, from the round's side of it. */
function reverseNote(t: TFunction, change: SyncChange, at: string | null) {
  // The rollback REMOVES a file the round added, and RESTORES one it removed.
  if (change.status === "removed") return t("sync.rollback.wasAdded");
  if (change.status === "added") return t("sync.rollback.wasRemoved");
  return at ? t("sync.rollback.backTo", { time: at }) : t("sync.rollback.backToSnapshot");
}

/** Five rows, then Show all; the expanded list scrolls inside the dialog. */
function ReversedList({
  changes,
  note,
}: {
  changes: SyncChange[];
  note: (change: SyncChange) => string;
}) {
  const { visible, shown, total, collapsed, expand, listClassName } = useLongList(changes, {
    scrollInside: true,
  });
  return (
    <div className={FILE_LIST} data-testid="sync-rollback-paths">
      <ul className={listClassName}>
        {visible.map((change) => (
          <li key={change.path} className={FILE_ROW}>
            <ChangeMark status={change.status} />
            <span className="min-w-0 flex-1 truncate font-mono text-xs text-text">
              {change.path}
            </span>
            <span className="shrink-0 text-xs text-text-subtle">{note(change)}</span>
          </li>
        ))}
      </ul>
      {collapsed ? <ShowAllRow shown={shown} total={total} onShowAll={expand} /> : null}
    </div>
  );
}

function KeptList({ paths }: { paths: string[] }) {
  const { t } = useTranslation();
  const { visible, shown, total, collapsed, expand, listClassName } = useLongList(paths, {
    scrollInside: true,
  });
  return (
    <div className="flex flex-col gap-2" data-testid="sync-rollback-kept">
      <span className="text-sm font-semibold text-text">{t("sync.rollback.kept")}</span>
      <div className={FILE_LIST}>
        <ul className={listClassName}>
          {visible.map((path) => (
            <li key={path} className={FILE_ROW}>
              <span className="min-w-0 flex-1 truncate font-mono text-xs text-text">{path}</span>
            </li>
          ))}
        </ul>
        {collapsed ? <ShowAllRow shown={shown} total={total} onShowAll={expand} /> : null}
      </div>
    </div>
  );
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
      description={
        plan.data
          ? t("sync.rollback.descriptionSnapshot", {
              snapshot: plan.data.snapshot,
              time: snapAt ? clockSeconds(snapAt) : "",
            })
          : t("sync.rollback.description")
      }
      confirmLabel={t("sync.rollback.confirm")}
      pendingLabel={t("sync.rollback.rollingBack")}
      variant="default"
      width="wide"
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
        <div className="flex flex-col gap-4" data-testid="sync-rollback-plan">
          {reverses.length > 0 ? (
            <div className="flex flex-col gap-2">
              <span className="text-sm font-semibold text-text">{t("sync.rollback.reverses")}</span>
              <ReversedList
                changes={reverses}
                note={(change) => reverseNote(t, change, snapAt ? clock(snapAt) : null)}
              />
            </div>
          ) : null}
          {plan.data.kept.length > 0 ? <KeptList paths={plan.data.kept} /> : null}
          <p className="flex items-start gap-2 text-xs leading-[1.45] text-text-muted">
            <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            {t("sync.rollback.follow", { time: when })}
          </p>
        </div>
      ) : null}
    </ConfirmDialog>
  );
}
