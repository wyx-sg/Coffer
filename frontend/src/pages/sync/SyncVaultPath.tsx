// frontend/src/pages/sync/SyncVaultPath.tsx
//
// Where the vault lives, and the one place it must not: inside a folder that
// Syncthing, iCloud or Dropbox also synchronises. Two tools syncing the same
// git repository corrupt it between them, so the daemon pauses sync there and
// this says why, with the path to move.
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";

export function SyncVaultPath({
  path,
  synchroniser,
}: {
  path: string;
  synchroniser: string | null;
}) {
  const { t } = useTranslation();
  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">
        {t("sync.remote.vaultPath")} <span className="font-mono">{path}</span>
      </p>
      {synchroniser ? (
        <Alert variant="warning" data-testid="sync-cloud-folder">
          <AlertTriangle aria-hidden />
          <AlertDescription>
            {t("sync.remote.cloudFolder", { tool: synchroniser, path })}
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
}
