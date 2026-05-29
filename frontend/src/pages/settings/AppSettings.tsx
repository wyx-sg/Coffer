import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { isTauri, getAutostartEnabled, setAutostartEnabled } from "@/lib/tauri";

/**
 * Desktop-app preferences. Tauri-only — SettingsLayout hides the tab in the
 * browser; if the route is reached directly there, it redirects to Data so
 * the user never lands on a blank pane. (The shim is auto-deployed on every
 * desktop launch; it needs no manual control here.)
 */
export function AppSettings() {
  const { t } = useTranslation();
  const [autostart, setAutostart] = useState<boolean | null>(null);
  const [autostartBusy, setAutostartBusy] = useState(false);
  const [autostartError, setAutostartError] = useState<string | null>(null);

  useEffect(() => {
    if (!isTauri()) return;
    // On a read failure, fall back to a known (off) state so the toggle
    // becomes interactive instead of stuck disabled, and surface the error.
    getAutostartEnabled()
      .then(setAutostart)
      .catch((e: unknown) => {
        setAutostart(false);
        setAutostartError(e instanceof Error ? e.message : String(e));
      });
  }, []);

  if (!isTauri()) return <Navigate to="/settings/data" replace />;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t("settings.app.autostart.title")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex items-center gap-3">
            <Switch
              id="autostart"
              checked={autostart === true}
              disabled={autostart === null || autostartBusy}
              onCheckedChange={async (v) => {
                setAutostartBusy(true);
                setAutostartError(null);
                try {
                  const actual = await setAutostartEnabled(v);
                  setAutostart(actual);
                } catch (e) {
                  setAutostartError(e instanceof Error ? e.message : String(e));
                } finally {
                  setAutostartBusy(false);
                }
              }}
            />
            <Label htmlFor="autostart">{t("settings.app.autostart.label")}</Label>
          </div>
          {autostartError ? (
            <p className="text-xs text-destructive" role="alert">
              {autostartError}
            </p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
