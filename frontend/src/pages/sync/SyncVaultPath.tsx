// frontend/src/pages/sync/SyncVaultPath.tsx
//
// "Vault on this Mac": where the vault lives, and the one place it must not —
// inside a folder that iCloud Drive, Dropbox or Syncthing also synchronises.
// Two tools syncing one git repository corrupt it between them, so the daemon
// pauses sync there and this row says why, naming the tool.
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { useFsActions } from "@/lib/fsActions";

export function SyncVaultPath({
  path,
  synchroniser,
}: {
  path: string;
  synchroniser: string | null;
}) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const fs = useFsActions();

  return (
    <div className="flex items-center justify-between gap-6 border-t border-border-subtle pt-4">
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="text-sm font-medium text-text">{t("sync.remote.vaultPath")}</span>
        {synchroniser ? (
          <p
            className="flex items-start gap-1.5 text-xs text-warning"
            data-testid="sync-cloud-folder"
          >
            <AlertTriangle className="mt-px size-3.5 shrink-0" aria-hidden />
            <span>
              <span className="font-mono">{path}</span> ·{" "}
              {t("sync.remote.cloudFolder", { tool: synchroniser })}
            </span>
          </p>
        ) : (
          <p className="text-xs text-text-muted">
            <span className="font-mono">{path}</span> · {t("sync.remote.notCloudFolder")}
          </p>
        )}
      </div>
      <Button
        type="button"
        variant="outline"
        onClick={() => void fs.reveal(path).catch(() => toast.error(t("fileActions.revealFailed")))}
      >
        {t("sync.remote.reveal")}
      </Button>
    </div>
  );
}
