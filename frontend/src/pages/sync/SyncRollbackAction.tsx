// frontend/src/pages/sync/SyncRollbackAction.tsx
//
// Undo one converge round, from the History row that describes it.
//
// Until this existed, a user whose vault had just been damaged by a round
// could see exactly what the round did — the History row lists every path —
// and had no way to undo it without opening a terminal. `coffer sync rollback`
// was the only door.
//
// The button belongs to ONE row, never to all of them: `POST /sync/rollback`
// reverses the round that left the newest pre-apply snapshot and takes no
// argument, so an Undo on every row would run the same call from each and undo
// a round the user was not pointing at. Which row that is is decided in
// `syncRunColumns.rollbackTargetId`.
//
// What the dialog has to say is what will come back, not that something will:
// the round's own applied paths, rendered by the same `SyncRoundPathList` the
// expanded row uses, so the list in the confirmation and the list in the row
// are visibly the same list.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Undo2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { RunRecord } from "@/lib/api/sync";
import { useRollbackRound } from "@/lib/hooks/useSync";
import { formatDateTime } from "@/lib/utils";
import { SyncRoundPathList } from "./SyncRoundPathList";

/** Paths past this are summarised — a dialog that scrolls past the confirm
 *  button is worse at answering "what is about to happen" than a count is.
 *  The same cap the held-round banner uses. */
const MAX_PATHS = 20;

export function SyncRollbackAction({ run }: { run: RunRecord }) {
  const { t } = useTranslation();
  const rollback = useRollbackRound();
  const [open, setOpen] = useState(false);
  const when = formatDateTime(run.finished_at);
  const applied = run.applied.changes;
  const shown = applied.slice(0, MAX_PATHS);
  const hidden = applied.length - shown.length;

  return (
    // The row opens its own detail on click; without this the click that
    // raises the dialog would also expand the row behind it.
    <div className="flex justify-end" onClick={(e) => e.stopPropagation()}>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        disabled={rollback.isPending}
      >
        <Undo2 className="mr-1.5 size-3.5" aria-hidden />
        {t("sync.rollback.action")}
      </Button>

      <ConfirmDialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          // A refusal read once should not greet the next attempt.
          if (!next) rollback.reset();
        }}
        title={t("sync.rollback.title")}
        description={t("sync.rollback.description", { when })}
        confirmLabel={rollback.isPending ? t("sync.rollback.undoing") : t("sync.rollback.confirm")}
        pending={rollback.isPending}
        error={rollback.error}
        onConfirm={() =>
          // Closes only in `onSuccess`, so a daemon that refuses the rollback
          // leaves the dialog up with its reason (agents/frontend.md §5).
          rollback.mutate(undefined, { onSuccess: () => setOpen(false) })
        }
      >
        {applied.length > 0 ? (
          <div className="space-y-1">
            <SyncRoundPathList
              titleKey="sync.rollback.willUndo"
              items={shown.map((c) => t(`sync.round.change.${c.status}`, { path: c.path }))}
              testId="sync-rollback-paths"
            />
            {hidden > 0 ? (
              <p className="text-xs text-muted-foreground">
                {t("sync.rollback.morePaths", { count: hidden })}
              </p>
            ) : null}
          </div>
        ) : (
          // A round can be the newest snapshot and still have applied nothing
          // here — it published, or it changed nothing at all. Saying so is
          // more use than an empty heading.
          <p className="text-sm text-muted-foreground">{t("sync.rollback.nothingApplied")}</p>
        )}
      </ConfirmDialog>
    </div>
  );
}
