// src/components/settings/about/UninstallSection.tsx
//
// Settings › About › Uninstall (spec web-ui "Offer uninstall on Settings ›
// About"; canvas 1.4.27–1.4.29). In the desktop app, Uninstall Coffer… opens
// the confirmation (`UninstallDialog`); `?uninstall=1` (and `&delete=1`) opens
// it for `coffer uninstall`. In a browser the page cannot remove the app, so it
// shows the command.
import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { CopyableCommand } from "@/components/settings/CopyableCommand";
import { SettingRow, SettingsSection } from "@/components/settings/SettingsLayout";
import { Button } from "@/components/ui/button";
import { uninstallAvailable } from "@/lib/shellUninstall";
import { UninstallDialog } from "./UninstallDialog";

export function UninstallSection() {
  const { t } = useTranslation();
  const inApp = uninstallAvailable();
  const { search } = useLocation();
  const [open, setOpen] = useState(false);
  const [deleteFirst, setDeleteFirst] = useState(false);
  // The shell navigates here for `coffer uninstall`, also while About is open.
  useEffect(() => {
    const params = new URLSearchParams(search);
    if (!inApp || params.get("uninstall") !== "1") return;
    setDeleteFirst(params.get("delete") === "1");
    setOpen(true);
  }, [inApp, search]);

  return (
    <SettingsSection title={t("settings.about.uninstall.title")} testId="settings-about-uninstall">
      {inApp ? (
        <SettingRow
          label={t("settings.about.uninstall.label")}
          description={t("settings.about.uninstall.description")}
        >
          <Button variant="outline" onClick={() => setOpen(true)}>
            {t("settings.about.uninstall.open")}
          </Button>
        </SettingRow>
      ) : (
        <SettingRow
          label={t("settings.about.uninstall.label")}
          description={t("settings.about.uninstall.browser")}
          layout="stack"
        >
          <CopyableCommand command="coffer uninstall" />
        </SettingRow>
      )}
      {inApp ? (
        <UninstallDialog
          key={String(deleteFirst)}
          open={open}
          onOpenChange={setOpen}
          deleteFirst={deleteFirst}
        />
      ) : null}
    </SettingsSection>
  );
}
