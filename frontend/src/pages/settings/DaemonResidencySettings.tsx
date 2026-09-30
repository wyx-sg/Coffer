// frontend/src/pages/settings/DaemonResidencySettings.tsx
//
// Settings → Daemon: whether Coffer's daemon starts at login — the Start at
// login row of the Startup section (spec web-ui "Set when the daemon runs on
// the Daemon tab").
//
// An agent calls Coffer from a terminal, an editor or a chat channel, mostly
// with no window open anywhere, so a daemon that exists only because something
// started it is down exactly when it is wanted — and whoever asks first pays
// the cold start. Starting it at login fixes that. Nothing ends it on its own:
// the daemon never stands down for being idle, so there is no idle window to
// offer here.
//
// The response says what is actually true afterwards rather than what was
// asked for.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { SettingRow } from "@/components/settings/SettingsLayout";
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import { useDaemonResidency, useSetDaemonResidency } from "@/lib/hooks/useDaemonResidency";

interface Props {
  /** The daemon cannot be reached: the switch cannot change. */
  disabled?: boolean;
}

export function DaemonResidencySettings({ disabled = false }: Props) {
  const { t } = useTranslation();
  const { data } = useDaemonResidency();
  const save = useSetDaemonResidency();
  // Until the daemon has answered, the switch is showing a default rather than
  // the setting. A click in that window would PUT that default over whatever
  // the daemon actually holds.
  const loaded = data !== undefined;

  // Local mirror so a click reads as instant; corrected from the response,
  // which is what is true rather than what was asked.
  const [autostart, setAutostart] = useState(false);

  useEffect(() => {
    if (!data) return;
    setAutostart(data.login_service_installed);
  }, [data]);

  const commit = (checked: boolean) => {
    setAutostart(checked);
    save.mutate(
      { login_service_installed: checked },
      // A switch that moved and stayed moved is a claim that the setting
      // changed. When the request failed it did not, and a switch left on
      // over an error message tells the user their daemon starts at login
      // when it does not.
      { onError: () => setAutostart(data?.login_service_installed ?? false) },
    );
  };

  const unsupported = data?.login_service_supported === false;

  return (
    <SettingRow
      label={t("settings.daemon.autostart")}
      description={
        unsupported ? t("settings.daemon.autostartUnsupported") : t("settings.daemon.autostartHelp")
      }
      status={
        save.error ? (
          <span className="text-xs text-danger" role="alert">
            {translateApiError(t, save.error)}
          </span>
        ) : null
      }
    >
      <Switch
        checked={autostart}
        disabled={disabled || !loaded || unsupported || save.isPending}
        onCheckedChange={commit}
        aria-label={t("settings.daemon.autostart")}
      />
    </SettingRow>
  );
}
