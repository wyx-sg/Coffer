// frontend/src/pages/sync/SyncMasterKeyCard.tsx
//
// Out-of-band master-key transfer (spec vault-sync "Never write the master key
// into the repository"). It lives on the Sync page rather than in Settings
// because its whole purpose is convergence: secrets sync as Fernet
// ciphertext only, so another machine can read what this one publishes exactly
// when it holds this same key.
//
// The two directions go through different hosts:
//
//   Export → a link to Settings › Security, which owns the passphrase-protected
//            backup (desktop app only, behind a presence check) and says so in
//            a browser.
//   Import → a hidden `<input type="file">`; its change handler reads
//            `file.text()`, asks the user to confirm — a different key makes
//            every secret stored under the current one unreadable — and
//            only then POSTs the material. Any host may do this.
//
// The key is never written into the synced repository under any setting.
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useImportMasterKey, useKeyFingerprint } from "@/lib/hooks/useSync";

export function SyncMasterKeyCard() {
  const { t } = useTranslation();
  const fileInput = useRef<HTMLInputElement>(null);
  // Local status lines: the mutations toast transport errors, but an empty
  // file never reaches the daemon, so that one is validated here.
  const [imported, setImported] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  // Key material read from the picked file, held while the confirmation is
  // open. Never persisted anywhere on the page; cleared as soon as it closes.
  const [pendingMaterial, setPendingMaterial] = useState<string | null>(null);
  const importKey = useImportMasterKey();
  const fingerprint = useKeyFingerprint();

  const reset = () => {
    setImported(null);
    setLocalError(null);
  };

  const onFileChosen = async (file: File | undefined) => {
    reset();
    if (!file) return;
    const material = (await file.text()).trim();
    if (!material) {
      setLocalError(t("sync.key.fileEmpty"));
      return;
    }
    setPendingMaterial(material);
  };

  const confirmImport = () => {
    const material = pendingMaterial;
    setPendingMaterial(null);
    if (!material) return;
    importKey.mutate(material, {
      // A key that still leaves references locked is the interesting case: it
      // means the ciphertext came from a THIRD machine holding another key.
      onSuccess: (res) =>
        setImported(
          res.locked_refs.length > 0
            ? t("sync.key.importedLocked", { count: res.locked_refs.length })
            : t("sync.key.imported"),
        ),
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("sync.key.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">{t("sync.key.hint")}</p>
        {/* The key's SHA-256 fingerprint (never the key): the machines table
            compares it for you, and this is the value it compares. */}
        {fingerprint.data?.fingerprint ? (
          <p className="text-sm" data-testid="key-fingerprint">
            <span className="text-muted-foreground">{t("sync.key.fingerprint")}: </span>
            <code className="font-mono">{fingerprint.data.fingerprint}</code>
            <span className="ml-2 text-xs text-muted-foreground">
              {t("sync.key.fingerprintHint")}
            </span>
          </p>
        ) : null}
        <div className="flex gap-2">
          <Button variant="secondary" asChild>
            <Link to="/settings/security">{t("sync.key.export")}</Link>
          </Button>
          <Button
            variant="secondary"
            onClick={() => fileInput.current?.click()}
            disabled={importKey.isPending}
          >
            {t("sync.key.import")}
          </Button>
          {/* Hidden on purpose: the Button above is the affordance, so the
              control keeps the same label it had with the native dialog. */}
          <input
            ref={fileInput}
            type="file"
            className="hidden"
            aria-label={t("sync.key.import")}
            onChange={(e) => {
              const file = e.target.files?.[0];
              // Reset first, so re-picking the SAME file fires change again.
              e.target.value = "";
              void onFileChosen(file);
            }}
          />
        </div>
        {imported ? (
          <p className="text-xs text-status-ok" role="status">
            {imported}
          </p>
        ) : null}
        {localError ? (
          <p className="text-xs text-destructive" role="alert">
            {localError}
          </p>
        ) : null}
      </CardContent>

      <ConfirmDialog
        open={pendingMaterial !== null}
        onOpenChange={(open) => {
          if (!open) setPendingMaterial(null);
        }}
        title={t("sync.key.importConfirmTitle")}
        description={t("sync.key.importConfirmBody")}
        confirmLabel={t("sync.key.import")}
        pending={importKey.isPending}
        onConfirm={confirmImport}
      />
    </Card>
  );
}
