// frontend/src/pages/settings/SyncMasterKeyCard.tsx
//
// Out-of-band master-key transfer (spec 010). Click → native dialog picks the
// path (save dialog for export, open dialog for import), the same on desktop
// (Tauri) and web (daemon picker, spec 004 FR-042 / ADR-036). A typed path
// field appears only as a fallback on hosts with no native dialog tool. The key
// never travels through the sync repo.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { pickOpenFile, pickSaveFile } from "@/lib/filePicker";
import { useExportMasterKey, useImportMasterKey, useKeyFingerprint } from "@/lib/hooks/useSync";

const DEFAULT_KEY_NAME = "coffer-master.key";

export function SyncMasterKeyCard() {
  const { t } = useTranslation();
  // manual mode is revealed only after a pick reports no native dialog tool.
  const [manual, setManual] = useState(false);
  const [keyPath, setKeyPath] = useState("");
  const importKey = useImportMasterKey();
  const exportKey = useExportMasterKey();
  const fingerprint = useKeyFingerprint();

  const onExport = async () => {
    if (manual) {
      if (keyPath) exportKey.mutate(keyPath);
      return;
    }
    const res = await pickSaveFile(DEFAULT_KEY_NAME);
    if (res.unavailable) {
      setManual(true);
      return;
    }
    if (res.path) exportKey.mutate(res.path);
  };

  const onImport = async () => {
    if (manual) {
      if (keyPath) importKey.mutate(keyPath);
      return;
    }
    const res = await pickOpenFile();
    if (res.unavailable) {
      setManual(true);
      return;
    }
    if (res.path) importKey.mutate(res.path);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.sync.masterKey")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-foreground/70">{t("settings.sync.masterKeyHint")}</p>
        {/* The key's SHA-256 fingerprint (never the key): compare it across
            machines after an export/import to confirm they hold the SAME key. */}
        {fingerprint.data?.present && (
          <p className="text-sm" data-testid="key-fingerprint">
            <span className="text-foreground/60">{t("settings.sync.keyFingerprint")}: </span>
            <code className="font-mono">{fingerprint.data.fingerprint}</code>
            <span className="ml-2 text-xs text-foreground/50">
              {t("settings.sync.keyFingerprintHint")}
            </span>
          </p>
        )}
        {manual && (
          <div className="space-y-2">
            <Label htmlFor="sync-key-path">{t("settings.sync.keyPath")}</Label>
            <Input
              id="sync-key-path"
              value={keyPath}
              placeholder="/path/to/coffer-master.key"
              onChange={(e) => setKeyPath(e.target.value)}
            />
            <p className="text-xs text-foreground/60">{t("settings.sync.keyPathManualHint")}</p>
          </div>
        )}
        <div className="flex gap-2">
          <Button
            variant="secondary"
            onClick={onExport}
            disabled={exportKey.isPending || (manual && !keyPath)}
          >
            {t("settings.sync.exportKey")}
          </Button>
          <Button
            variant="secondary"
            onClick={onImport}
            disabled={importKey.isPending || (manual && !keyPath)}
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
