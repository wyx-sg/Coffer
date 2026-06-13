// frontend/src/pages/settings/SyncMasterKeyCard.tsx
//
// Out-of-band master-key transfer (spec 010). On the desktop app a native
// save/open file dialog picks the path (click → choose, like mature software);
// in the browser (no native picker for arbitrary paths) it falls back to a
// path text field. The key never travels through the sync repo.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { isTauri } from "@/lib/tauri";
import { useExportMasterKey, useImportMasterKey } from "@/lib/hooks/useSync";

const DEFAULT_KEY_NAME = "coffer-master.key";

export function SyncMasterKeyCard() {
  const { t } = useTranslation();
  const [keyPath, setKeyPath] = useState("");
  const importKey = useImportMasterKey();
  const exportKey = useExportMasterKey();

  const onExport = async () => {
    if (isTauri()) {
      const { save } = await import("@tauri-apps/plugin-dialog");
      const path = await save({ defaultPath: DEFAULT_KEY_NAME });
      if (path) exportKey.mutate(path);
      return;
    }
    if (keyPath) exportKey.mutate(keyPath);
  };

  const onImport = async () => {
    if (isTauri()) {
      const { open } = await import("@tauri-apps/plugin-dialog");
      const path = await open({ multiple: false, directory: false });
      if (typeof path === "string") importKey.mutate(path);
      return;
    }
    if (keyPath) importKey.mutate(keyPath);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.sync.masterKey")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-foreground/70">{t("settings.sync.masterKeyHint")}</p>
        {!isTauri() && (
          <div className="space-y-2">
            <Label htmlFor="sync-key-path">{t("settings.sync.keyPath")}</Label>
            <Input
              id="sync-key-path"
              value={keyPath}
              placeholder="/path/to/coffer-master.key"
              onChange={(e) => setKeyPath(e.target.value)}
            />
          </div>
        )}
        <div className="flex gap-2">
          <Button
            variant="secondary"
            onClick={onExport}
            disabled={exportKey.isPending || (!isTauri() && !keyPath)}
          >
            {t("settings.sync.exportKey")}
          </Button>
          <Button
            variant="secondary"
            onClick={onImport}
            disabled={importKey.isPending || (!isTauri() && !keyPath)}
          >
            {t("settings.sync.importKey")}
          </Button>
        </div>
        {exportKey.data && (
          <p className="text-xs text-green-600" role="status">
            {t("settings.sync.keyExported", { path: exportKey.data.path })}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
