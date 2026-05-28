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

  useEffect(() => {
    if (!isTauri()) return;
    void getAutostartEnabled().then(setAutostart);
  }, []);

  if (!isTauri()) return <Navigate to="/settings/data" replace />;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t("settings.app.autostart.title")}</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center gap-3">
          <Switch
            id="autostart"
            checked={autostart === true}
            disabled={autostart === null || autostartBusy}
            onCheckedChange={async (v) => {
              setAutostartBusy(true);
              try {
                const actual = await setAutostartEnabled(v);
                setAutostart(actual);
              } finally {
                setAutostartBusy(false);
              }
            }}
          />
          <Label htmlFor="autostart">{t("settings.app.autostart.label")}</Label>
        </CardContent>
      </Card>
    </div>
  );
}
