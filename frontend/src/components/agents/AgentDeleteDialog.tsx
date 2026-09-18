// frontend/src/components/agents/AgentDeleteDialog.tsx — spec agent-registry.
// Delete-confirmation for AgentDetailPage: the shared ConfirmDialog plus the
// `useRemoveAgent` mutation it drives, so the page wires only the open state
// and where to go afterwards. A component rather than a block on the page
// because AgentDetailPage is at its file-size limit.
//
// It was a hand-rolled six-element Dialog — a copy of ConfirmDialog with
// nothing added — which meant it silently opted out of the convention that a
// confirmation closes only on success. Going through the primitive, it gets
// both the closing rule and the inline error.
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useRemoveAgent } from "@/lib/hooks/useAgents";

export function AgentDeleteDialog({
  uid,
  name,
  open,
  onOpenChange,
  onDeleted,
}: {
  /** The agent to delete. */
  uid: string;
  /** Its label, which the confirmation reads out. */
  name: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeleted: () => void;
}) {
  const { t } = useTranslation();
  const remove = useRemoveAgent();

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) remove.reset();
      }}
      title={t("agents.removeConfirm", { name })}
      description={t("agents.removeConfirmBody")}
      confirmLabel={remove.isPending ? t("common.deleting") : t("common.delete")}
      pending={remove.isPending}
      error={remove.error}
      onConfirm={() =>
        // Closes only on success, so a failure leaves the dialog up with the
        // reason on it.
        remove.mutate(uid, {
          onSuccess: () => {
            onOpenChange(false);
            onDeleted();
          },
        })
      }
    />
  );
}
