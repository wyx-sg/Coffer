// frontend/src/pages/sync/SyncStopSyncing.tsx
//
// "Stop syncing" forgets the remote. The vault, its history and the remote
// repository itself are untouched — it only stops this machine from syncing
// with it — but it is still asked, because every machine setting up again
// has to join from scratch.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useClearSyncRemote } from "@/lib/hooks/useSync";

export function SyncStopSyncing({ disabled }: { disabled: boolean }) {
  const { t } = useTranslation();
  const clear = useClearSyncRemote();
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button type="button" variant="ghost" disabled={disabled} onClick={() => setOpen(true)}>
        {t("sync.remote.stop")}
      </Button>
      <ConfirmDialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) clear.reset();
        }}
        title={t("sync.remote.stopTitle")}
        description={t("sync.remote.stopBody")}
        confirmLabel={t("sync.remote.stop")}
        pending={clear.isPending}
        error={clear.error}
        onConfirm={() => clear.mutate(undefined, { onSuccess: () => setOpen(false) })}
      />
    </>
  );
}
