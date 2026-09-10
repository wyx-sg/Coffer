// frontend/src/pages/settings/SyncMasterKeyCard.tsx
//
// Out-of-band master-key transfer (spec 010), using the browser's own file
// mechanisms rather than a native dialog driven by the daemon:
//
//   Export → ask the daemon for the key MATERIAL, wrap it in a Blob and click a
//            hidden `<a download>`, so the file lands wherever the browser puts
//            downloads.
//   Import → a hidden `<input type="file">`; its change handler reads
//            `file.text()` and POSTs the material.
//
// The browser hands us contents directly, so no absolute path has to survive a
// round-trip through the daemon. The key is still never written into an export
// bundle — a machine holding ciphertext but not the key reports
// credentials_locked, so the key comes across separately.
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import { useExportMasterKey, useImportMasterKey, useKeyFingerprint } from "@/lib/hooks/useSync";

const DEFAULT_KEY_NAME = "coffer-master.key";

/** Save `text` to the user's downloads as `filename`, via a transient anchor. */
function downloadText(text: string, filename: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: "application/octet-stream" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function SyncMasterKeyCard() {
  const { t } = useTranslation();
  const fileInput = useRef<HTMLInputElement>(null);
  // Local status lines: the mutations report transport errors, but an empty
  // file never reaches the daemon, so that one is validated here.
  const [exported, setExported] = useState<string | null>(null);
  const [imported, setImported] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const importKey = useImportMasterKey();
  const exportKey = useExportMasterKey();
  const fingerprint = useKeyFingerprint();

  const onExport = () => {
    setExported(null);
    setImported(false);
    setLocalError(null);
    exportKey.mutate(undefined, {
      onSuccess: (res) => {
        downloadText(res.material, DEFAULT_KEY_NAME);
        setExported(DEFAULT_KEY_NAME);
      },
    });
  };

  const onFileChosen = async (file: File | undefined) => {
    setExported(null);
    setImported(false);
    setLocalError(null);
    if (!file) return;
    const material = (await file.text()).trim();
    if (!material) {
      setLocalError(t("settings.sync.keyFileEmpty"));
      return;
    }
    importKey.mutate(material, { onSuccess: () => setImported(true) });
  };

  const error = exportKey.error ?? importKey.error;

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
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onExport} disabled={exportKey.isPending}>
            {t("settings.sync.exportKey")}
          </Button>
          <Button
            variant="secondary"
            onClick={() => fileInput.current?.click()}
            disabled={importKey.isPending}
          >
            {t("settings.sync.importKey")}
          </Button>
          {/* Hidden on purpose: the Button above is the affordance, so the
              control keeps the same label it had with the native dialog. */}
          <input
            ref={fileInput}
            type="file"
            className="hidden"
            aria-label={t("settings.sync.importKey")}
            onChange={(e) => {
              const file = e.target.files?.[0];
              // Reset first, so re-picking the SAME file fires change again.
              e.target.value = "";
              void onFileChosen(file);
            }}
          />
        </div>
        {exported && (
          <p className="text-xs text-green-600" role="status">
            {t("settings.sync.keyExported", { name: exported })}
          </p>
        )}
        {imported && (
          <p className="text-xs text-green-600" role="status">
            {t("settings.sync.keyImported")}
          </p>
        )}
        {(localError || error) && (
          <p className="text-xs text-destructive" role="alert">
            {localError ?? translateApiError(t, error)}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
