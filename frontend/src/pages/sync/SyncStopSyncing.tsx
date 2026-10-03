// frontend/src/pages/sync/SyncStopSyncing.tsx
//
// "Stop syncing this Mac" (6.4.27) forgets the remote here. The vault, its
// history and the repository are untouched and the other Macs keep syncing, so
// it runs at once with no question: the toast offers Undo (6.4.29), which puts
// the remote back exactly as it was — a Mac that has not set up again since.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import { useClearSyncRemote, useRestoreSyncRemote } from "@/lib/hooks/useSync";
import { SettingsRow, SettingsSection } from "./SyncSettingsParts";

export function SyncStopSyncing() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const clear = useClearSyncRemote();
  const restore = useRestoreSyncRemote();

  const stop = () =>
    clear.mutate(undefined, {
      onSuccess: (result) =>
        toast.info(
          t("sync.remote.stop.done"),
          result.restorable ? { undo: () => restore.mutate() } : undefined,
        ),
      onError: (error) => toast.error(translateApiError(t, error)),
    });

  return (
    <SettingsSection title={t("sync.remote.stop.label")} description={t("sync.remote.stop.hint")}>
      <SettingsRow
        label={t("sync.remote.stop.confirm")}
        wide={false}
        control={
          <Button type="button" variant="danger" size="sm" loading={clear.isPending} onClick={stop}>
            {t("sync.remote.stop.confirm")}
          </Button>
        }
      />
    </SettingsSection>
  );
}
