// src/components/settings/security/MasterKeyBackupRow.tsx — "Back up the master key" on Settings › Security.
//
// The export runs in the desktop app only: the shell asks for Touch ID, asks
// for a folder natively and writes a 0600 file itself, so the key never
// reaches this page — the page learns only where the file went and the key's
// fingerprint. In a browser the row names the app instead of offering a
// control that could only fail.
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
import { useRevealPath } from "@/lib/hooks/useSecurity";
import { useExportMasterKeyBackup } from "@/lib/hooks/useSync";
import { presenceAvailable, type MasterKeyBackup } from "@/lib/tauri";

import { SettingRow } from "@/components/settings/SettingsLayout";

/** The file's folder and name, for "Saved <file> to <dir>". */
function splitPath(path: string): { dir: string; file: string } {
  const i = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return i < 0
    ? { dir: "", file: path }
    : { dir: path.slice(0, i) || "/", file: path.slice(i + 1) };
}

export function MasterKeyBackupRow() {
  const { t } = useTranslation();
  const exportKey = useExportMasterKeyBackup();
  const [exported, setExported] = useState<MasterKeyBackup | null>(null);

  return (
    <SettingRow
      label={t("settings.security.backup.title")}
      description={t("settings.security.backup.description")}
    >
      {presenceAvailable() ? (
        <Button
          variant="outline"
          disabled={exportKey.isPending}
          onClick={() => exportKey.mutate(undefined, { onSuccess: setExported })}
        >
          <KeyRound aria-hidden />
          {t("settings.security.backup.export")}
        </Button>
      ) : (
        <span className="text-xs text-text-muted" data-testid="master-key-open-in-app">
          {t("credentials.presence.openInApp")}
        </span>
      )}
      <ExportedDialog backup={exported} onClose={() => setExported(null)} />
    </SettingRow>
  );
}

function ExportedDialog({
  backup,
  onClose,
}: {
  backup: MasterKeyBackup | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const reveal = useRevealPath();
  const { dir, file } = splitPath(backup?.path ?? "");

  return (
    <Dialog open={backup !== null} onOpenChange={(open) => (open ? null : onClose())}>
      <DialogContent className="max-w-[420px]">
        <DialogHeader>
          <DialogTitle>{t("settings.security.backup.exportedTitle")}</DialogTitle>
          <DialogDescription>
            {t("settings.security.backup.exportedBody", { file, dir })}
          </DialogDescription>
        </DialogHeader>
        <p className="text-sm text-text">{t("settings.security.backup.exportedHint")}</p>
        <p className="text-xs text-text-muted">
          {t("settings.security.backup.fingerprint")}{" "}
          <code className="font-mono">{backup?.fingerprint}</code>
        </p>
        <DialogFooter>
          <Button
            variant="outline"
            disabled={reveal.isPending || !backup}
            onClick={() => backup && reveal.mutate(backup.path)}
          >
            <FolderSearch aria-hidden />
            {t("settings.security.backup.showInFinder")}
          </Button>
          <Button onClick={onClose}>{t("settings.security.backup.done")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
