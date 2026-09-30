// frontend/src/pages/sync/SyncStopSyncing.tsx
//
// "Stop syncing this Mac" (6.5.26) forgets the remote here. The vault, its
// history and the repository are untouched and the other Macs keep syncing —
// but it is still asked, because setting up again means joining again. The
// dialog names what is forgotten: the remote and the last round.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { ConfirmDialog, ConfirmFacts } from "@/components/ui/confirm-dialog";
import type { SyncStatus } from "@/lib/api/sync";
import { useClearSyncRemote } from "@/lib/hooks/useSync";
import { roundMoment } from "./syncMachineTimes";
import { statusLabel } from "./syncRoundStatus";

export function SyncStopSyncing({ status }: { status: SyncStatus }) {
  const { t, i18n } = useTranslation();
  const clear = useClearSyncRemote();
  const [open, setOpen] = useState(false);
  const last = status.last_round;
  const lastAt = last?.finished_at ?? last?.started_at ?? null;

  return (
    <div className="flex items-center justify-between gap-6">
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="text-sm font-medium text-text">{t("sync.remote.stop.label")}</span>
        <span className="text-xs text-text-muted">{t("sync.remote.stop.hint")}</span>
      </div>
      <Button type="button" variant="outline" onClick={() => setOpen(true)}>
        {t("sync.remote.stop.open")}
      </Button>
      <ConfirmDialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) clear.reset();
        }}
        title={t("sync.remote.stop.title")}
        description={t("sync.remote.stop.body")}
        confirmLabel={t("sync.remote.stop.confirm")}
        pending={clear.isPending}
        error={clear.error}
        onConfirm={() => clear.mutate(undefined, { onSuccess: () => setOpen(false) })}
      >
        <ConfirmFacts
          items={[
            {
              label: t("sync.remote.stop.remote"),
              value: <span className="font-mono text-xs">{status.remote?.url ?? "—"}</span>,
            },
            {
              label: t("sync.remote.stop.lastRound"),
              value:
                last && lastAt
                  ? `${roundMoment(lastAt, new Date(), t, i18n.language)} · ${statusLabel(t, last.status)}`
                  : t("sync.machines.never"),
            },
          ]}
        />
      </ConfirmDialog>
    </div>
  );
}
