// frontend/src/components/history/VaultRestoreDialog.tsx
//
// Restore this version… asks first (spec web-ui "Show a vault file's history
// on a History tab"): it names the version and says the file — or every file
// of the folder, with those added since removed — goes back to it as a NEW
// version, so nothing in the history is lost. Confirming writes it through the
// vault (POST /vault/restore) stating the newest version the tab listed, so a
// file changed since is refused and the refusal stays in the dialog.
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import type { VaultVersionOut } from "@/lib/api/vault";
import { useRestoreVaultVersion } from "@/lib/hooks/useVaultHistory";
import { whenLabel } from "@/lib/knowledge/changes";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The history's path: a file, or a folder ending in `/`. */
  path: string;
  /** The version to put back. */
  target: VaultVersionOut;
  /** The newest version the tab listed — what the restore expects is current. */
  newest: VaultVersionOut;
}

export function VaultRestoreDialog({ open, onOpenChange, path, target, newest }: Props) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const restore = useRestoreVaultVersion();
  const when = whenLabel(t, target.time, i18n.language);
  const folder = path.endsWith("/");

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) restore.reset();
        onOpenChange(next);
      }}
      variant="default"
      title={t("history.restoreTitle")}
      description={t(folder ? "history.restoreFolderBody" : "history.restoreFileBody", { when })}
      confirmLabel={t("history.restoreConfirm")}
      pendingLabel={t("history.restoring")}
      errorTitle={t("history.restoreFailed")}
      onConfirm={() =>
        restore
          .mutateAsync({ path, version: target.version, expected_current: newest.version })
          .then(() => toast.success(t("history.restored", { when })))
      }
    />
  );
}
