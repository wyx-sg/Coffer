// frontend/src/pages/sync/SyncPendingBanner.tsx
//
// The deletion circuit breaker held a round (spec vault-sync `## Safety`), and
// the answer the user gives here can destroy data either way — so the
// DIRECTION leads, in the title, not in a detail line:
//
//   apply   — the remote would delete this much of YOUR vault.
//   publish — THIS vault would delete this much of the remote, which is the
//             direction that matters when this machine is the damaged one. A
//             machine just reinstalled or restored from a backup is missing
//             its documents, not rid of them, and confirming would take every
//             other machine down with it. That warning is shown unconditionally
//             on `publish`, because the user cannot be expected to reconstruct
//             it from a list of paths. That direction also offers a third
//             answer — REBUILD — because for a machine whose files really are
//             gone, confirm spreads the loss and reject refuses the same round
//             forever.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { PendingConfirmation } from "@/lib/api/sync";
import { useConfirmRound, useRebuildFromRemote, useRejectRound } from "@/lib/hooks/useSync";
import { formatDateTime } from "@/lib/utils";

/** Paths past this are summarised rather than listed — the banner has to stay
 *  readable, and the breach counts already carry the magnitude. */
const MAX_PATHS = 20;

export function SyncPendingBanner({ pending }: { pending: PendingConfirmation }) {
  const { t } = useTranslation();
  const confirm = useConfirmRound();
  const reject = useRejectRound();
  const rebuild = useRebuildFromRemote();
  const [confirmRebuild, setConfirmRebuild] = useState(false);
  const busy = confirm.isPending || reject.isPending || rebuild.isPending;
  const publishes = pending.direction === "publish";
  const shown = pending.paths.slice(0, MAX_PATHS);
  const hidden = pending.paths.length - shown.length;

  return (
    <Alert
      className="border-status-err/40 bg-status-err/5"
      data-testid="sync-pending-banner"
      role="alert"
    >
      <AlertTriangle className="size-4" aria-hidden />
      <AlertTitle>
        {t(publishes ? "sync.pending.titlePublish" : "sync.pending.titleApply")}
      </AlertTitle>
      <AlertDescription className="space-y-3">
        <p className="text-muted-foreground">
          {t(publishes ? "sync.pending.bodyPublish" : "sync.pending.bodyApply")}
        </p>
        {publishes ? (
          <p className="font-medium text-status-err">{t("sync.pending.reinstallWarning")}</p>
        ) : null}

        <div className="space-y-1">
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
          <p className="font-medium">{t("sync.pending.paths")}</p>
          <ul className="space-y-0.5">
            {shown.map((path) => (
              <li key={path} className="font-mono text-xs">
                {path}
              </li>
            ))}
          </ul>
          {hidden > 0 ? (
            <p className="text-xs text-muted-foreground">
              {t("sync.pending.morePaths", { count: hidden })}
            </p>
          ) : null}
        </div>

        <p className="text-xs text-muted-foreground">
          {t("sync.pending.raisedAt", { when: formatDateTime(pending.raised_at) })}
        </p>

        <div className="flex flex-wrap gap-2">
          <Button variant="destructive" disabled={busy} onClick={() => confirm.mutate()}>
            {confirm.isPending ? t("sync.pending.confirming") : t("sync.pending.confirm")}
          </Button>
          <Button variant="secondary" disabled={busy} onClick={() => reject.mutate()}>
            {reject.isPending ? t("sync.pending.rejecting") : t("sync.pending.reject")}
          </Button>
          {/* Only on `publish`: rebuilding is the answer for a machine whose
              own files are gone, and it makes no sense in the other direction.
              It discards local-only documents, so it asks first. */}
          {publishes ? (
            <Button variant="ghost" disabled={busy} onClick={() => setConfirmRebuild(true)}>
              {rebuild.isPending ? t("sync.pending.rebuilding") : t("sync.pending.rebuild")}
            </Button>
          ) : null}
        </div>
      </AlertDescription>

      <ConfirmDialog
        open={confirmRebuild}
        onOpenChange={setConfirmRebuild}
        title={t("sync.pending.rebuildTitle")}
        description={t("sync.pending.rebuildConfirm")}
        confirmLabel={t("sync.pending.rebuild")}
        pending={busy}
        onConfirm={() => {
          setConfirmRebuild(false);
          rebuild.mutate();
        }}
      />
    </Alert>
  );
}
