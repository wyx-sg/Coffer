// frontend/src/pages/settings/SyncBundleCard.tsx
//
// Settings → Sync → Export / Import (spec 010). Two buttons, each opening the
// daemon-hosted native directory picker (spec 004 FR-042 / ADR-036) to name a
// bundle directory; the export one is gated by an opt-in "include credentials"
// switch, off by default, because an export directory is easy to leave
// somewhere careless. Both operations report the backend's summary: counts per
// area, the resources that failed, and the bundle path.
//
// A typed-path field appears only as a fallback on hosts with no native dialog
// tool — the same shape SyncMasterKeyCard uses, since there is no in-app
// directory browser wired into this card.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import { pickDirectory } from "@/lib/filePicker";
import { useExportVault, useImportVault, type BundleResult } from "@/lib/hooks/useSync";

function BundleSummary({ result, titleKey }: { result: BundleResult; titleKey: string }) {
  const { t } = useTranslation();
  const counts = Object.entries(result.counts).filter(([, n]) => n > 0);
  return (
    <div className="space-y-1 rounded-md border p-3 text-sm" data-testid="bundle-summary">
      <p role="status">{t(titleKey, { path: result.path })}</p>
      {counts.length > 0 && (
        <p className="text-foreground/70">
          {counts.map(([area, n]) => `${t(`settings.sync.areas.${area}`, area)}: ${n}`).join(" · ")}
        </p>
      )}
      {result.failures.length > 0 && (
        <ul className="list-inside list-disc text-amber-600">
          {result.failures.map((f) => (
            <li key={f.ref}>
              {t("settings.sync.bundleFailure", { ref: f.ref, reason: f.reason })}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function SyncBundleCard() {
  const { t } = useTranslation();
  // manual mode is revealed only after a pick reports no native dialog tool.
  const [manual, setManual] = useState(false);
  const [dirPath, setDirPath] = useState("");
  const [withCredentials, setWithCredentials] = useState(false);
  const exportVault = useExportVault();
  const importVault = useImportVault();
  const busy = exportVault.isPending || importVault.isPending;

  const resolvePath = async (): Promise<string | null> => {
    if (manual) return dirPath || null;
    const res = await pickDirectory();
    if (res.unavailable) {
      setManual(true);
      return null;
    }
    return res.path;
  };

  const onExport = async () => {
    const path = await resolvePath();
    if (path) exportVault.mutate({ path, withCredentials });
  };

  const onImport = async () => {
    const path = await resolvePath();
    if (path) importVault.mutate(path);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.sync.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-foreground/70">{t("settings.sync.description")}</p>

        <div className="flex items-center justify-between gap-4">
          <Label htmlFor="sync-with-credentials">{t("settings.sync.withCredentials")}</Label>
          <Switch
            id="sync-with-credentials"
            checked={withCredentials}
            disabled={busy}
            onCheckedChange={setWithCredentials}
          />
        </div>
        <p className="text-xs text-foreground/60">{t("settings.sync.withCredentialsHint")}</p>

        {manual && (
          <div className="space-y-2">
            <Label htmlFor="sync-bundle-path">{t("settings.sync.bundlePath")}</Label>
            <Input
              id="sync-bundle-path"
              value={dirPath}
              placeholder="/path/to/coffer-bundle"
              onChange={(e) => setDirPath(e.target.value)}
            />
            <p className="text-xs text-foreground/60">{t("settings.sync.bundlePathManualHint")}</p>
          </div>
        )}

        <div className="flex gap-2">
          <Button variant="secondary" onClick={onExport} disabled={busy || (manual && !dirPath)}>
            {t("settings.sync.exportVault")}
          </Button>
          <Button variant="secondary" onClick={onImport} disabled={busy || (manual && !dirPath)}>
            {t("settings.sync.importVault")}
          </Button>
        </div>

        {exportVault.error && (
          <p className="text-sm text-red-600">{translateApiError(t, exportVault.error)}</p>
        )}
        {importVault.error && (
          <p className="text-sm text-red-600">{translateApiError(t, importVault.error)}</p>
        )}
        {exportVault.data && (
          <BundleSummary result={exportVault.data} titleKey="settings.sync.exported" />
        )}
        {importVault.data && (
          <BundleSummary result={importVault.data} titleKey="settings.sync.imported" />
        )}
      </CardContent>
    </Card>
  );
}
