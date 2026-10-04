// src/components/settings/security/MasterKeyBackupRow.tsx — "Back up the master key" on Settings › Security.
//
// The export runs in the desktop app only (spec secret "Release plaintext only
// to a present human in the desktop app"): the page asks for a passphrase,
// then the shell asks for Touch ID, asks for a folder natively, and the daemon
// writes `coffer-master-key.cfk` — the key encrypted under that passphrase —
// so the key never reaches this page. The page learns only where the file
// went. In a browser the row names the app on a disabled button instead of
// offering a control that could only fail.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FolderSearch, KeyRound } from "lucide-react";

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
import { useExportMasterKey, useRevealPath } from "@/lib/hooks/useSecurity";
import { presenceAvailable, type MasterKeyBackup } from "@/lib/tauri";

import { SettingRow } from "@/components/settings/SettingsLayout";

import { tildePath } from "./fingerprint";

/** The daemon refuses a shorter passphrase (`MASTER_KEY_PASSPHRASE_TOO_SHORT`). */
const MIN_PASSPHRASE_LENGTH = 8;

/** The file's folder and name, for "Saved <file> to <dir>". */
function splitPath(path: string): { dir: string; file: string } {
  const i = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return i < 0
    ? { dir: "", file: path }
    : { dir: path.slice(0, i) || "/", file: path.slice(i + 1) };
}

export function MasterKeyBackupRow() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const inApp = presenceAvailable();

  return (
    <SettingRow
      label={t("settings.security.backup.title")}
      description={
        inApp
          ? t("settings.security.backup.description")
          : `${t("settings.security.backup.description")} ${t("settings.security.backup.onlyInApp")}`
      }
    >
      {inApp ? (
        <Button variant="outline" onClick={() => setOpen(true)}>
          <KeyRound aria-hidden />
          {t("settings.security.backup.export")}
        </Button>
      ) : (
        <Button variant="outline" disabled data-testid="master-key-open-in-app">
          {t("settings.security.backup.openInApp")}
        </Button>
      )}
      {inApp ? <ExportDialog open={open} onClose={() => setOpen(false)} /> : null}
    </SettingRow>
  );
}

function ExportDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const exportKey = useExportMasterKey();
  const [passphrase, setPassphrase] = useState("");
  const [repeat, setRepeat] = useState("");
  const [exported, setExported] = useState<MasterKeyBackup | null>(null);

  const close = () => {
    // Nothing typed outlives the dialog.
    setPassphrase("");
    setRepeat("");
    setExported(null);
    exportKey.reset();
    onClose();
  };

  const tooShort = passphrase.length > 0 && passphrase.length < MIN_PASSPHRASE_LENGTH;
  const mismatch = repeat.length > 0 && repeat !== passphrase;
  const ready = passphrase.length >= MIN_PASSPHRASE_LENGTH && repeat === passphrase;
  // A cancelled Touch ID prompt or folder picker is the person changing their
  // mind, not a failure to report.
  const failure =
    exportKey.error && String(exportKey.error.message ?? exportKey.error) !== "cancelled"
      ? String(exportKey.error.message ?? exportKey.error)
      : null;

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? null : close())}>
      <DialogContent>
        {exported ? (
          <Exported backup={exported} onDone={close} />
        ) : (
          <form
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (ready) exportKey.mutate(passphrase, { onSuccess: setExported });
            }}
          >
            <DialogHeader>
              <DialogTitle>{t("settings.security.backup.dialogTitle")}</DialogTitle>
            </DialogHeader>
            <div className="rounded-lg bg-surface-sunken px-3 py-2.5">
              <p className="text-sm font-medium text-text">
                {t("settings.security.backup.safeTitle")}
              </p>
              <DialogDescription className="text-xs">
                {t("settings.security.backup.safeBody")}
              </DialogDescription>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="backup-passphrase">{t("settings.security.backup.passphrase")}</Label>
              <PasswordInput
                id="backup-passphrase"
                autoComplete="new-password"
                value={passphrase}
                onChange={(e) => setPassphrase(e.target.value)}
              />
              <span className={tooShort ? "text-xs text-danger" : "text-xs text-text-muted"}>
                {tooShort
                  ? t("settings.security.backup.tooShort", { count: MIN_PASSPHRASE_LENGTH })
                  : t("settings.security.backup.passphraseHint")}
              </span>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="backup-passphrase-repeat">
                {t("settings.security.backup.repeat")}
              </Label>
              <PasswordInput
                id="backup-passphrase-repeat"
                autoComplete="new-password"
                value={repeat}
                onChange={(e) => setRepeat(e.target.value)}
              />
              {mismatch ? (
                <span className="text-xs text-danger">
                  {t("settings.security.backup.mismatch")}
                </span>
              ) : null}
            </div>
            {failure ? (
              <p className="text-xs text-danger" role="alert">
                {failure}
              </p>
            ) : null}
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={close}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={!ready || exportKey.isPending}>
                {exportKey.isPending
                  ? t("settings.security.backup.exporting")
                  : t("settings.security.backup.submit")}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Exported({ backup, onDone }: { backup: MasterKeyBackup; onDone: () => void }) {
  const { t } = useTranslation();
  const reveal = useRevealPath();
  const { dir, file } = splitPath(backup.path);

  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("settings.security.backup.exportedTitle")}</DialogTitle>
        <DialogDescription>
          {t("settings.security.backup.exportedBody", { file, dir: tildePath(dir) })}
        </DialogDescription>
      </DialogHeader>
      <p className="text-sm text-text">{t("settings.security.backup.exportedHint")}</p>
      <DialogFooter>
        <Button
          variant="outline"
          disabled={reveal.isPending}
          onClick={() => reveal.mutate(backup.path)}
        >
          <FolderSearch aria-hidden />
          {t("settings.security.backup.showInFinder")}
        </Button>
        <Button onClick={onDone}>{t("settings.security.backup.done")}</Button>
      </DialogFooter>
    </>
  );
}
