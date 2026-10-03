// frontend/src/pages/settings/DaemonSettings.tsx
//
// Settings → Daemon (canvas 1.4.15, 1.4.16; spec web-ui "Show and manage the
// daemon on Settings → Daemon"): the background process that serves the
// agents and this page. The status card (state, version, channel, port, start
// time, executable) with the host's restart, then Startup — Start at login and
// the editable port of the next start. It reads the one status poll the
// sidebar footer and the offline banner share. There is no token row (the
// token is on Settings › Security), no troubleshooting section (the daemon log
// is Activity's Daemon log tab, Copy diagnostics is on Settings › About) and no
// stop control. While the daemon cannot be reached, Start at login and Port
// are disabled.
import { useTranslation } from "react-i18next";

import { DaemonPortRow } from "@/components/settings/daemon/DaemonPortRow";
import { DaemonStatusCard } from "@/components/settings/daemon/DaemonStatusCard";
import {
  SETTINGS_STACK,
  SettingsSection,
  SettingsTabHeader,
} from "@/components/settings/SettingsLayout";
import { useDaemonState } from "@/components/settings/daemon/useDaemonState";
import { useDaemonStatus } from "@/lib/hooks/useDaemon";
import { inDesktopShell } from "@/lib/tauri";
import { DaemonResidencySettings } from "./DaemonResidencySettings";

export function DaemonSettings() {
  const { t } = useTranslation();
  const state = useDaemonState();
  const { data: status } = useDaemonStatus();
  const inShell = inDesktopShell();
  const unreachable = state.kind === "offline" || state.kind === "connecting";

  return (
    <div className="flex flex-col gap-5">
      <SettingsTabHeader title={t("settings.tabs.daemon")} intro={t("settings.daemonTab.intro")} />
      <div className={SETTINGS_STACK}>
        <DaemonStatusCard state={state} status={status} inShell={inShell} />
        <SettingsSection title={t("settings.daemonTab.startup")} testId="settings-daemon-startup">
          <DaemonResidencySettings disabled={unreachable} />
          <DaemonPortRow disabled={unreachable} />
        </SettingsSection>
      </div>
    </div>
  );
}
