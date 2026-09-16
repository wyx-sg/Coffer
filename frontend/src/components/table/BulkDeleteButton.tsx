// frontend/src/components/table/BulkDeleteButton.tsx
//
// The delete action of a selection bar: the destructive outline button plus the
// confirmation it opens, written once. Five bulk bars carried their own copy of
// both — the same button classes and the same six-element Dialog — differing
// only in the confirmation copy, which is the one thing that genuinely belongs
// to the caller.
//
// The caller still owns the deletion itself (which endpoint, which query keys
// to invalidate, whether the selection clears), because that is the part that
// is really per-kind. This owns the affordance and the confirm step.
import { useState } from "react";
import { Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

/** The destructive tint every "this removes something" button in a bulk bar
 *  wears. Exported so the few non-delete destructive actions (uninstall a
 *  plugin, delete an unmanaged skill from disk) match it exactly. */
export const DESTRUCTIVE_ACTION_CLASS =
  "text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive";

interface Props {
  title: string;
  description: string;
  pending?: boolean;
  /** Runs the deletion. Handed straight to ConfirmDialog, so the convention
   *  applies here too: the dialog closes when this RESOLVES and stays open
   *  with the reason if it rejects. A bulk run settles every row and resolves
   *  with counts (`useBulkMutate`), reporting partial failure in its own
   *  summary toast — so in practice it closes and the toast explains. A run
   *  that rejects outright is the case this used to close on regardless. */
  onConfirm: () => void | Promise<void>;
}

export function BulkDeleteButton({ title, description, pending = false, onConfirm }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button
        type="button"
        size="sm"
        variant="outline"
        className={DESTRUCTIVE_ACTION_CLASS}
        disabled={pending}
        onClick={() => setOpen(true)}
      >
        <Trash2 className="mr-1.5 size-3.5" />
        {t("common.bulk.delete")}
      </Button>

      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title={title}
        description={description}
        confirmLabel={pending ? t("common.deleting") : t("common.bulk.delete")}
        pending={pending}
        onConfirm={() => Promise.resolve(onConfirm())}
      />
    </>
  );
}
