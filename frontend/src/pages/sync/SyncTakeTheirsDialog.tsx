// frontend/src/pages/sync/SyncTakeTheirsDialog.tsx
//
// "Take the other's" overwrites this Mac's version, so it asks first — and
// shows what it would change here: the unified diff from this Mac's version
// to theirs (`GET /sync/stop/files/versions`), fetched when the dialog opens.
// A binary file has no diff to show, and says so.
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useFileVersions } from "@/lib/hooks/useSyncStop";

interface Props {
  path: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pending: boolean;
  error: unknown;
  onConfirm: () => void;
}

export function SyncTakeTheirsDialog({
  path,
  open,
  onOpenChange,
  pending,
  error,
  onConfirm,
}: Props) {
  const { t } = useTranslation();
  const versions = useFileVersions(path, open);
  const data = versions.data;

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("sync.conflicts.takeTheirsTitle")}
      description={t("sync.conflicts.takeTheirsBody", { path })}
      confirmLabel={t("sync.conflicts.takeTheirs")}
      pending={pending}
      error={error ?? versions.error}
      onConfirm={onConfirm}
    >
      {versions.isLoading ? (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : data?.binary ? (
        <p className="text-sm text-muted-foreground">{t("sync.conflicts.binary")}</p>
      ) : data ? (
        <pre
          className="max-h-72 overflow-auto rounded bg-muted p-2 font-mono text-xs"
          data-testid="sync-take-theirs-diff"
        >
          {data.take_theirs || t("sync.conflicts.noDiff")}
        </pre>
      ) : null}
    </ConfirmDialog>
  );
}
