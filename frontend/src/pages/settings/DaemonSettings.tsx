// frontend/src/pages/settings/DaemonSettings.tsx
//
// Settings → Daemon: the daemon's state and when it runs. The shell moved the
// Start at login card here from General (spec web-ui "Set when the daemon runs
// on the Daemon tab") and reads the state from the one status poll the footer
// and the offline banner share. The rest of the tab — host-dependent restart
// and the editable port — lands with its own work item (change
// revise-web-ui-ia tasks 3.3 / 3.3c).
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { StatusDot } from "@/components/status/StatusDot";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useDaemonFooterState } from "@/components/shell/useDaemonFooterState";
import { useDaemonStatus } from "@/lib/hooks/useDaemon";
import { formatDateTime } from "@/lib/utils";
import { DaemonResidencySettings } from "./DaemonResidencySettings";

const EMPTY = "—";

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex gap-3">
      <span className="w-32 shrink-0 text-text-muted">{label}</span>
      <span className="min-w-0 break-all">{value}</span>
    </div>
  );
}

export function DaemonSettings() {
  const { t } = useTranslation();
  const state = useDaemonFooterState();
  const { data: status } = useDaemonStatus();
  const running = state.kind === "running";
  const word =
    state.kind === "running"
      ? t("nav.daemon.running", { port: state.port })
      : t(`nav.daemon.${state.kind}`);
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t("settings.daemonTab.title")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm" data-testid="settings-daemon-status">
          <Row
            label={t("settings.daemonTab.state")}
            value={
              <span className="inline-flex items-center gap-2">
                <StatusDot
                  tone={
                    running
                      ? "ok"
                      : state.kind === "offline"
                        ? "err"
                        : state.kind === "stopping"
                          ? "warn"
                          : "off"
                  }
                />
                {word}
              </span>
            }
          />
          <Row label={t("settings.daemonTab.port")} value={running ? state.port : EMPTY} />
          <Row label={t("settings.daemonTab.version")} value={status?.version ?? EMPTY} />
          <Row
            label={t("settings.daemonTab.startedAt")}
            value={status?.started_at ? formatDateTime(status.started_at) : EMPTY}
          />
        </CardContent>
      </Card>
      <DaemonResidencySettings />
    </div>
  );
}
