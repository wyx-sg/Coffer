// frontend/src/components/memory/DeletePartitionDialog.tsx — confirm deleting a partition whose repository is gone.
//
// Only an unresolvable partition is offered for deletion (spec memory "Report
// unresolvable partitions"): any other one comes back on the next Update
// memory, so deleting it would be a promise the page could not keep. The
// dialog closes only in the delete's `onSuccess`; a failure stays on screen
// with its reason (the mutation's `error`).
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { PartitionOut } from "@/lib/api/memoryTypes";
import { useDeletePartition } from "@/lib/hooks/useMemory";
import { displayName } from "@/lib/resourceTitle";

interface Props {
  /** The partition to delete; `null` keeps the dialog closed. */
  partition: PartitionOut | null;
  onClose: () => void;
  /** Runs after a successful delete (e.g. leave the partition's page). */
  onDeleted?: () => void;
}

export function DeletePartitionDialog({ partition, onClose, onDeleted }: Props) {
  const { t } = useTranslation();
  const del = useDeletePartition();
  const name = partition ? displayName(partition) : "";

  return (
    <ConfirmDialog
      open={partition !== null}
      onOpenChange={(open) => {
        if (!open) {
          del.reset();
          onClose();
        }
      }}
      title={t("memory.delete.title", { name })}
      description={t("memory.delete.body", { count: partition?.note_count ?? 0 })}
      confirmLabel={t("memory.delete.confirm")}
      variant="destructive"
      pending={del.isPending}
      error={del.error}
      onConfirm={() => {
        if (!partition) return;
        del.mutate(partition.uid, {
          onSuccess: () => {
            onClose();
            onDeleted?.();
          },
        });
      }}
    >
      <p className="text-sm text-text-muted">{t("memory.delete.untouched")}</p>
    </ConfirmDialog>
  );
}
