// frontend/src/pages/sync/SyncVaultPath.tsx
//
// "Vault on this Mac" (6.4.27): where the vault lives, and the one place it
// must not — inside a folder that iCloud Drive, Dropbox or Syncthing also
// synchronises. Two tools syncing one git repository corrupt it between them,
// so the daemon pauses sync there; the section then says which tool and the
// row offers "Move the vault…" next to Reveal in Finder.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FolderOpen } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { useFsActions } from "@/lib/fsActions";
import type { SyncStatus } from "@/lib/api/sync";
import { SyncMoveVaultDialog } from "./SyncMoveVaultDialog";
import { SettingsRow, SettingsSection } from "./SyncSettingsParts";

export function SyncVaultPath({ status }: { status: SyncStatus }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const fs = useFsActions();
  const [moving, setMoving] = useState(false);
  const { synchroniser } = status;
  const path = status.vault_real_path ?? status.vault_path;

  return (
    <SettingsSection
      title={t("sync.remote.vaultPath")}
      description={
        synchroniser ? (
          <span className="text-warning" data-testid="sync-cloud-folder">
            {t("sync.remote.cloudFolder", { tool: synchroniser })}
          </span>
        ) : (
          t("sync.remote.notCloudFolder")
        )
      }
    >
      <SettingsRow
        label={<span className="whitespace-nowrap font-mono text-xs">{path}</span>}
        wide={false}
        control={
          <div className="flex items-center gap-2">
            {synchroniser ? (
              <Button type="button" variant="outline" size="sm" onClick={() => setMoving(true)}>
                {t("sync.problem.cloud_folder.move")}
              </Button>
            ) : null}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() =>
                void fs.reveal(path).catch(() => toast.error(t("fileActions.revealFailed")))
              }
            >
              <FolderOpen aria-hidden />
              {t("sync.remote.reveal")}
            </Button>
          </div>
        }
      />
      <SyncMoveVaultDialog open={moving} onOpenChange={setMoving} status={status} />
    </SettingsSection>
  );
}
