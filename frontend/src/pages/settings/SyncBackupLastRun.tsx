// frontend/src/pages/settings/SyncBackupLastRun.tsx
//
// The last backup run's story, read straight off GET /sync/status: what the run
// achieved, when, which commit it left behind, and why it failed.
//
// Purely presentational — it fetches nothing and decides nothing — because the
// failure line is the one place a user looks when a backup stops working, and
// it should be readable without the card's form state in the way. The error
// text arrives already scrubbed of any push token by the daemon; nothing here
// needs to redact, and nothing here should start.
import { useTranslation } from "react-i18next";
import type { BackupRun } from "@/lib/hooks/useSync";
import { formatDateTime } from "@/lib/utils";

interface Props {
  lastRun: BackupRun | null;
}

export function SyncBackupLastRun({ lastRun }: Props) {
  const { t } = useTranslation();

  if (!lastRun) {
    return (
      <div className="space-y-1 text-sm" data-testid="backup-last-run">
        <p className="text-foreground/60">{t("settings.sync.backup.noRunYet")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-1 text-sm" data-testid="backup-last-run">
      <p role="status">
        {t("settings.sync.backup.lastRun", {
          status: t(`settings.sync.backup.runStatus.${lastRun.status}`, lastRun.status),
          when: lastRun.ran_at ? formatDateTime(lastRun.ran_at) : t("settings.sync.backup.never"),
        })}
      </p>
      {lastRun.commit && (
        <p className="text-xs text-foreground/60">
          {t("settings.sync.backup.commit", { commit: lastRun.commit })}
        </p>
      )}
      {lastRun.error && (
        <p className="text-xs text-destructive" role="alert">
          {lastRun.error}
        </p>
      )}
    </div>
  );
}
