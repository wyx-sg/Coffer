// frontend/src/pages/sync/SyncDeletionActions.tsx
//
// The two answers to a held round (6.5.09), each naming how many files it
// touches. Delete asks again (6.5.28: which files, who deleted them, and that
// a snapshot is taken first), because it destroys; Restore does not, because
// it destroys nothing. Either answer continues the round.
import { useState, type ReactNode } from "react";
import { Trash2, Undo2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { ConfirmDialog, ConfirmFacts } from "@/components/ui/confirm-dialog";
import type { SyncHold } from "@/lib/api/sync";
import { useConfirmHold, useRestoreHold } from "@/lib/hooks/useSyncStop";

interface Props {
  hold: SyncHold;
  /** Who deleted the files: the other Macs' names, or "this Mac". */
  who: string;
  onDone: () => void;
}

function Option(props: { title: string; body: string; action: ReactNode; testId: string }) {
  return (
    <div
      className="flex min-w-0 flex-1 basis-0 flex-col items-start gap-2 rounded-xl border border-border bg-surface-raised p-4"
      data-testid={props.testId}
    >
      <p className="text-sm font-label text-text">{props.title}</p>
      <p className="text-xs text-text-muted">{props.body}</p>
      <div className="mt-1">{props.action}</div>
    </div>
  );
}

export function SyncDeletionActions({ hold, who, onDone }: Props) {
  const { t } = useTranslation();
  const confirm = useConfirmHold();
  const restore = useRestoreHold();
  const [confirming, setConfirming] = useState(false);
  const count = hold.paths.length;
  const dir = hold.direction;
  const busy = confirm.isPending || restore.isPending;
  const folders = hold.groups.map((g) => (g.folder.endsWith("/") ? g.folder : `${g.folder}/`));

  return (
    <>
      <div className="flex flex-col gap-3 sm:flex-row">
        <Option
          testId="sync-deletions-delete"
          title={t(`sync.deletions.delete.title.${dir}`)}
          body={t(`sync.deletions.delete.body.${dir}`, { machine: who })}
          action={
            <Button
              type="button"
              variant="destructive"
              size="sm"
              disabled={busy}
              onClick={() => setConfirming(true)}
            >
              {t("sync.deletions.delete.button", { count })}
            </Button>
          }
        />
        <Option
          testId="sync-deletions-restore"
          title={t("sync.deletions.restore.title")}
          body={t(`sync.deletions.restore.body.${dir}`, { machine: who })}
          action={
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy}
              loading={restore.isPending}
              onClick={() => restore.mutate(undefined, { onSuccess: onDone })}
            >
              <Undo2 aria-hidden />
              {restore.isPending
                ? t("sync.deletions.restore.pending")
                : t("sync.deletions.restore.button", { count })}
            </Button>
          }
        />
      </div>
      <ConfirmDialog
        open={confirming}
        onOpenChange={(next) => {
          setConfirming(next);
          if (!next) confirm.reset();
        }}
        title={
          dir === "outgoing"
            ? t("sync.deletions.confirm.titleOutgoing", { count })
            : t("sync.deletions.confirm.titleIncoming", { count })
        }
        description={t(`sync.deletions.confirm.body.${dir}`, { machine: who })}
        confirmLabel={t("sync.deletions.confirm.button", { count })}
        confirmIcon={<Trash2 aria-hidden />}
        pendingLabel={t("sync.deletions.confirm.pending")}
        pending={confirm.isPending}
        error={confirm.error}
        onConfirm={() =>
          confirm.mutate(undefined, {
            onSuccess: () => {
              setConfirming(false);
              onDone();
            },
          })
        }
      >
        <ConfirmFacts
          items={[
            {
              label: t("sync.deletions.confirm.files"),
              value: (
                <>
                  {t("sync.deletions.confirm.filesValue", {
                    count,
                    folders: t("sync.deletions.folders", { count: folders.length }),
                  })}{" "}
                  · <span className="font-mono text-xs">{folders.join(", ")}</span>
                </>
              ),
            },
            { label: t("sync.deletions.confirm.deletedBy"), value: who },
            {
              label: t("sync.deletions.confirm.snapshot"),
              value: t("sync.deletions.confirm.snapshotValue"),
            },
          ]}
        />
      </ConfirmDialog>
    </>
  );
}
