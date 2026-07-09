// frontend/src/pages/settings/SyncStatusLine.tsx
//
// The status strip of the Sync settings panel (spec 010): badge, last-sync
// time, and the locked-credentials / quarantined-imports hints.
import { useTranslation } from "react-i18next";

import { StatusBadge, type StatusTone } from "@/components/StatusBadge";
import type { SyncStatus } from "@/lib/hooks/useSync";

const SYNC_TONE: Record<string, StatusTone> = {
  clean: "success",
  conflicted: "warning",
  credentials_locked: "warning",
  error: "danger",
  syncing: "info",
  unconfigured: "neutral",
};

export function SyncStatusLine({ status }: { status: SyncStatus }) {
  const { t } = useTranslation();
  const tone: StatusTone = SYNC_TONE[status.status] ?? "neutral";

  return (
    <div className="rounded-md border p-3 text-sm">
      <span className="text-foreground/60">{t("settings.sync.status")}: </span>
      <span role="status">
        <StatusBadge
          tone={tone}
          label={t(`settings.sync.statuses.${status.status}`)}
          pulse={status.status === "syncing"}
        />
      </span>
      {status.last_sync_at && (
        <span className="ml-2 text-foreground/50">
          {t("settings.sync.lastSync")}: {new Date(status.last_sync_at).toLocaleString()}
        </span>
      )}
      {status.locked_refs.length > 0 && (
        <p className="mt-1 text-amber-600">
          {t("settings.sync.lockedHint", { refs: status.locked_refs.join(", ") })}
        </p>
      )}
      {status.quarantined_refs.length > 0 && (
        <p className="mt-1 text-amber-600">
          {t("settings.sync.quarantinedHint", { refs: status.quarantined_refs.join(", ") })}
        </p>
      )}
      {status.last_error && <p className="mt-1 text-red-600">{status.last_error}</p>}
    </div>
  );
}
