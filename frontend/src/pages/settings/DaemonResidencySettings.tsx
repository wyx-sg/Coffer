// frontend/src/pages/settings/DaemonResidencySettings.tsx
//
// Settings → General: what starts Coffer's daemon, and what ends it.
//
// The two rows are one question. An agent calls Coffer from a terminal, an
// editor or a chat channel, mostly with no window open anywhere, so a daemon
// that exists only because something started it is down exactly when it is
// wanted — and whoever asks first pays the cold start. Starting it at login
// fixes that and creates the opposite problem, a process that survives every
// weekend nobody worked, which the idle window is the ceiling on.
//
// Both settings are written together (one PUT), and the response says what is
// actually true afterwards rather than what was asked for.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { translateApiError } from "@/lib/api/errors";
import { useDaemonResidency, useSetDaemonResidency } from "@/lib/hooks/useDaemonResidency";

/** The idle windows offered, in hours. `null` — never — is its own option. */
const IDLE_OPTIONS = [1, 4, 12, 24, 72] as const;
const NEVER = "never";

export function DaemonResidencySettings() {
  const { t } = useTranslation();
  const { data } = useDaemonResidency();
  const save = useSetDaemonResidency();
  // Until the daemon has answered, the controls below are showing defaults
  // rather than settings. A click in that window would PUT those defaults
  // over whatever the daemon actually holds — turning "never stand down"
  // into twelve hours, for instance, without anyone asking for it.
  const loaded = data !== undefined;

  // Local mirror so a click reads as instant; corrected from the response,
  // which is what is true rather than what was asked.
  const [autostart, setAutostart] = useState(false);
  const [idle, setIdle] = useState<string>(String(IDLE_OPTIONS[2]));

  useEffect(() => {
    if (!data) return;
    setAutostart(data.login_service_installed);
    setIdle(data.idle_shutdown_hours == null ? NEVER : String(data.idle_shutdown_hours));
  }, [data]);

  /** Put the controls back to what the daemon last told us. */
  const resync = () => {
    setAutostart(data?.login_service_installed ?? false);
    setIdle(data?.idle_shutdown_hours == null ? NEVER : String(data.idle_shutdown_hours));
  };

  const commit = (next: { autostart?: boolean; idle?: string }) => {
    const wantAutostart = next.autostart ?? autostart;
    const wantIdle = next.idle ?? idle;
    if (next.autostart !== undefined) setAutostart(next.autostart);
    if (next.idle !== undefined) setIdle(next.idle);
    save.mutate(
      {
        login_service_installed: wantAutostart,
        idle_shutdown_hours: wantIdle === NEVER ? null : Number(wantIdle),
      },
      // A control that moved and stayed moved is a claim that the setting
      // changed. When the request failed it did not, and a switch left on
      // over an error message tells the user their daemon starts at login
      // when it does not.
      { onError: resync },
    );
  };

  const unsupported = data?.login_service_supported === false;
  // `coffer daemon idle set 3` is legal and this list does not offer 3. A
  // Select with no matching item renders empty, so the setting the user has
  // would be the one thing the page cannot show them.
  const options: string[] = IDLE_OPTIONS.map(String);
  if (idle !== NEVER && !options.includes(idle)) options.push(idle);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.daemon.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex items-center justify-between gap-4">
          <div className="space-y-0.5">
            <p className="text-sm font-medium">{t("settings.daemon.autostart")}</p>
            <p className="text-sm text-muted-foreground">
              {unsupported
                ? t("settings.daemon.autostartUnsupported")
                : t("settings.daemon.autostartHelp")}
            </p>
          </div>
          <Switch
            checked={autostart}
            disabled={!loaded || unsupported || save.isPending}
            onCheckedChange={(checked) => commit({ autostart: checked })}
            aria-label={t("settings.daemon.autostart")}
          />
        </div>

        <div className="flex items-center justify-between gap-4">
          <div className="space-y-0.5">
            <p className="text-sm font-medium">{t("settings.daemon.idle")}</p>
            <p className="text-sm text-muted-foreground">{t("settings.daemon.idleHelp")}</p>
          </div>
          <Select value={idle} onValueChange={(v) => commit({ idle: v })} disabled={!loaded}>
            <SelectTrigger className="w-44" aria-label={t("settings.daemon.idle")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {options.map((hours) => (
                <SelectItem key={hours} value={hours}>
                  {t("settings.daemon.idleHours", { count: Number(hours) })}
                </SelectItem>
              ))}
              <SelectItem value={NEVER}>{t("settings.daemon.idleNever")}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {save.error ? (
          <p className="text-sm text-destructive">{translateApiError(t, save.error)}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
