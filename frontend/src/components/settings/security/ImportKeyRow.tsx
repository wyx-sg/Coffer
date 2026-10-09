// src/components/settings/security/ImportKeyRow.tsx — "Import a master key" on Settings › Security.
//
// Spec secret "Import a master key after showing whose key it is". The
// import runs in the desktop app only: installing a key needs a presence check
// the shell signs (spec secret "Release plaintext only to a present human in
// the desktop app"), so a browser shows "Open the Coffer app" instead. The flow
// is one dialog:
//
//   1. Choose… — a hidden `<input type="file">`; the page reads the file's
//      text and asks the daemon whose key it holds (`/secrets/key/import/preview`),
//      which replaces nothing. The dialog then shows this Mac's key beside the
//      file's, marked "same" or "different".
//   2. Passphrase — only for a `.cfk` backup (a bare key has none).
//   3. Replace key — installs it; the answer says how many stored secrets the
//      key opens and which still cannot be decrypted, shown in the same dialog.
//
// The file's text and the passphrase live in this dialog's state only and are
// cleared when it closes.
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";
import { Download } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { translateApiError } from "@/lib/api/errors";
import type { KeyImport, KeyPreview } from "@/lib/api/security";
import { useImportKeyFile, usePreviewKeyImport } from "@/lib/hooks/useSecurity";
import { presenceAvailable } from "@/lib/tauri";

import { SettingRow } from "@/components/settings/SettingsLayout";

import { formatFingerprint } from "./fingerprint";
import { ImportedKeyResult } from "./ImportedKeyResult";

export function ImportKeyRow() {
  const { t } = useTranslation();
  const inApp = presenceAvailable();
  // `?import=1`: the desktop app opened this page for `coffer secret import-key`; the
  // person still picks the file, types the passphrase and passes the presence check here.
  const { search } = useLocation();
  const [open, setOpen] = useState(
    () => inApp && new URLSearchParams(search).get("import") === "1",
  );

  return (
    <SettingRow
      label={t("settings.security.import.title")}
      description={t("settings.security.import.description")}
    >
      {inApp ? (
        <Button variant="outline" onClick={() => setOpen(true)}>
          <Download aria-hidden />
          {t("settings.security.import.button")}
        </Button>
      ) : (
        <Button variant="outline" disabled data-testid="master-key-import-open-in-app">
          {t("settings.security.import.openInApp")}
        </Button>
      )}
      {inApp ? <ImportDialog open={open} onClose={() => setOpen(false)} /> : null}
    </SettingRow>
  );
}

function ImportDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const fileInput = useRef<HTMLInputElement>(null);
  const preview = usePreviewKeyImport();
  const importKey = useImportKeyFile();
  const [fileName, setFileName] = useState<string | null>(null);
  const [material, setMaterial] = useState<string | null>(null);
  const [passphrase, setPassphrase] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [result, setResult] = useState<KeyImport | null>(null);

  const close = () => {
    setFileName(null);
    setMaterial(null);
    setPassphrase("");
    setLocalError(null);
    setResult(null);
    preview.reset();
    importKey.reset();
    onClose();
  };

  const onFileChosen = async (file: File | undefined) => {
    if (!file) return;
    preview.reset();
    importKey.reset();
    setLocalError(null);
    setFileName(file.name);
    const text = (await file.text()).trim();
    if (!text) {
      setMaterial(null);
      setLocalError(t("settings.security.import.fileEmpty"));
      return;
    }
    setMaterial(text);
    preview.mutate(text);
  };

  const seen: KeyPreview | undefined = preview.data;
  const needsPassphrase = seen?.protected === true;
  const ready =
    material !== null && seen !== undefined && (!needsPassphrase || passphrase.length > 0);
  const error = localError
    ? localError
    : preview.error
      ? translateApiError(t, preview.error)
      : importKey.error && String(importKey.error.message ?? importKey.error) !== "cancelled"
        ? translateApiError(t, importKey.error)
        : null;

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? null : close())}>
      <DialogContent>
        {result ? (
          <ImportedKeyResult result={result} onDone={close} />
        ) : (
          <form
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (!ready || material === null) return;
              importKey.mutate(
                { material, passphrase: needsPassphrase ? passphrase : null },
                { onSuccess: setResult },
              );
            }}
          >
            <DialogHeader>
              <DialogTitle>
                {seen?.same
                  ? t("settings.security.import.title")
                  : t("settings.security.import.dialogTitle")}
              </DialogTitle>
              <DialogDescription>{t("settings.security.import.dialogBody")}</DialogDescription>
            </DialogHeader>
            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold text-text">
                {t("settings.security.import.keyFile")}
              </span>
              <div className="flex items-center gap-2">
                <code
                  className="flex h-control-md min-w-0 grow items-center truncate rounded-md border border-border bg-surface-raised px-2.5 font-mono text-xs text-text"
                  data-testid="key-file-name"
                >
                  {fileName ?? t("settings.security.import.noFile")}
                </code>
                <Button type="button" variant="outline" onClick={() => fileInput.current?.click()}>
                  {t("settings.security.import.choose")}
                </Button>
                <input
                  ref={fileInput}
                  type="file"
                  className="hidden"
                  aria-label={t("settings.security.import.keyFile")}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    // Reset first, so re-picking the same file fires change again.
                    e.target.value = "";
                    void onFileChosen(file);
                  }}
                />
              </div>
            </div>
            {needsPassphrase ? (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="import-passphrase">
                  {t("settings.security.import.passphrase")}
                </Label>
                <PasswordInput
                  id="import-passphrase"
                  autoComplete="off"
                  value={passphrase}
                  onChange={(e) => {
                    importKey.reset();
                    setPassphrase(e.target.value);
                  }}
                />
                <span className="text-xs text-text-muted">
                  {t("settings.security.import.passphraseHint")}
                </span>
              </div>
            ) : null}
            {seen ? (
              <dl className="grid grid-cols-[120px_minmax(0,1fr)] gap-x-3 gap-y-2 rounded-lg bg-surface-sunken px-3 py-2.5 text-sm">
                <dt className="text-xs text-text-muted">{t("settings.security.import.current")}</dt>
                <dd>
                  <code className="font-mono text-xs text-text">
                    {seen.current_fingerprint
                      ? formatFingerprint(seen.current_fingerprint)
                      : t("settings.security.import.none")}
                  </code>
                </dd>
                <dt className="text-xs text-text-muted">{t("settings.security.import.inFile")}</dt>
                <dd data-testid="key-in-file">
                  <code className="font-mono text-xs text-text">
                    {formatFingerprint(seen.fingerprint)}
                  </code>{" "}
                  <span className={seen.same ? "text-xs text-text-muted" : "text-xs text-warning"}>
                    ·{" "}
                    {seen.same
                      ? t("settings.security.import.same")
                      : t("settings.security.import.different")}
                  </span>
                </dd>
              </dl>
            ) : null}
            {error ? (
              <p className="text-xs text-danger" role="alert">
                {error}
              </p>
            ) : null}
            <DialogFooter className="items-center">
              <span className="mr-auto text-xs text-text-muted">
                {t("settings.security.import.recorded")}
              </span>
              <Button type="button" variant="ghost" onClick={close}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={!ready || importKey.isPending}>
                {importKey.isPending
                  ? t("settings.security.import.importing")
                  : seen?.same
                    ? t("settings.security.import.importSame")
                    : t("settings.security.import.replace")}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
