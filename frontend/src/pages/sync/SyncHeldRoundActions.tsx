// frontend/src/pages/sync/SyncHeldRoundActions.tsx
//
// The three answers to a held round, on the row of the round that is held.
//
// These used to be a banner on a Status tab. The banner is gone, and so is the
// tab: a round the deletion guard stopped is not a state beside the history —
// it IS the newest row of it, and splitting "what is waiting" from "what has
// happened" meant reading one situation in two places.
//
// Only ONE row may carry these, and `syncRunRows.heldRoundId` decides which.
// `POST /sync/confirm` acts on the vault's current pending state rather than on
// a round named in the request, so a historical row that merely ENDED held
// must not offer them — and several always will, because the timer re-raises
// one unanswered situation as a new round every pass.
//
// Confirm opens a dialog because the row cannot carry what the answer costs:
// which direction, which areas, and the paths themselves. Reject does not,
// because it is the answer that destroys nothing — it discards the round and
// the next pass raises it again. Rebuild asks, and only on `publish`, where
// the question it answers ("my files really are gone") is the one that makes
// sense.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { PendingConfirmation } from "@/lib/api/sync";
import { useConfirmRound, useRebuildFromRemote, useRejectRound } from "@/lib/hooks/useSync";
import { formatDateTime } from "@/lib/utils";
import { SyncRoundPathList } from "./SyncRoundPathList";

/** Paths past this are summarised. A dialog that scrolls past its own confirm
 *  button answers "what is about to happen" worse than a count does. */
const MAX_PATHS = 20;

export function SyncHeldRoundActions({ pending }: { pending: PendingConfirmation }) {
  const { t } = useTranslation();
  const confirm = useConfirmRound();
  const reject = useRejectRound();
  const rebuild = useRebuildFromRemote();
  const [confirming, setConfirming] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);

  const publishes = pending.direction === "publish";
  const busy = confirm.isPending || reject.isPending || rebuild.isPending;
  const shown = pending.paths.slice(0, MAX_PATHS);
  const hidden = pending.paths.length - shown.length;

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <Button variant="destructive" size="sm" disabled={busy} onClick={() => setConfirming(true)}>
        {confirm.isPending ? t("sync.pending.confirming") : t("sync.pending.confirm")}
      </Button>
      <Button variant="secondary" size="sm" disabled={busy} onClick={() => reject.mutate()}>
        {reject.isPending ? t("sync.pending.rejecting") : t("sync.pending.reject")}
      </Button>
      {publishes ? (
        <Button variant="ghost" size="sm" disabled={busy} onClick={() => setRebuilding(true)}>
          {rebuild.isPending ? t("sync.pending.rebuilding") : t("sync.pending.rebuild")}
        </Button>
      ) : null}

      <ConfirmDialog
        open={confirming}
        onOpenChange={(next) => {
          setConfirming(next);
          // A refusal read once should not greet the next attempt.
          if (!next) confirm.reset();
        }}
        title={t(publishes ? "sync.pending.titlePublish" : "sync.pending.titleApply")}
        description={t(publishes ? "sync.pending.bodyPublish" : "sync.pending.bodyApply")}
        confirmLabel={confirm.isPending ? t("sync.pending.confirming") : t("sync.pending.confirm")}
        pending={busy}
        error={confirm.error}
        onConfirm={() =>
          // Closes only in `onSuccess`, so a daemon that refuses leaves the
          // dialog up with its reason (agents/frontend.md §5).
          confirm.mutate(undefined, { onSuccess: () => setConfirming(false) })
        }
      >
        <div className="space-y-3">
          {/* Unconditional on `publish`: the reader cannot reconstruct from a
              path list that a machine missing its documents is about to take
              every other machine down with it. */}
          {publishes ? (
            <p className="text-sm font-medium text-status-err">
              {t("sync.pending.reinstallWarning")}
            </p>
          ) : null}

          <div className="space-y-1 text-sm">
            <p className="font-medium">{t("sync.pending.breaches")}</p>
            <ul className="space-y-0.5 text-muted-foreground">
              {pending.breaches.map((breach) => (
                <li key={breach.area}>
                  {t("sync.pending.breach", {
                    area: t(`sync.areas.${breach.area}`, breach.area),
                    deleted: breach.deleted,
                    total: breach.total,
                  })}
                </li>
              ))}
            </ul>
          </div>

          <div className="space-y-1">
            <SyncRoundPathList
              titleKey="sync.pending.paths"
              items={shown}
              testId="sync-held-paths"
            />
            {hidden > 0 ? (
              <p className="text-xs text-muted-foreground">
                {t("sync.pending.morePaths", { count: hidden })}
              </p>
            ) : null}
          </div>

          <p className="text-xs text-muted-foreground">
            {t("sync.pending.raisedAt", { when: formatDateTime(pending.raised_at) })}
          </p>
        </div>
      </ConfirmDialog>

      <ConfirmDialog
        open={rebuilding}
        onOpenChange={(next) => {
          setRebuilding(next);
          if (!next) rebuild.reset();
        }}
        title={t("sync.pending.rebuildTitle")}
        description={t("sync.pending.rebuildConfirm")}
        confirmLabel={rebuild.isPending ? t("sync.pending.rebuilding") : t("sync.pending.rebuild")}
        pending={busy}
        error={rebuild.error}
        onConfirm={() => rebuild.mutate(undefined, { onSuccess: () => setRebuilding(false) })}
      />
    </div>
  );
}
