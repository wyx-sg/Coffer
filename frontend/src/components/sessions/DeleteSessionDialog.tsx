// src/components/sessions/DeleteSessionDialog.tsx — the confirmation before a
// conversation or an agent's session is deleted (spec chat "Rename and delete
// a conversation through its agent", agent-registry "Open an agent's sessions
// from its Sessions tab"). It names the row and says what Delete does: the
// session goes from the agent as well and cannot be recovered; the files the
// agent changed stay. It closes only when the delete has succeeded.
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { SessionRowData } from "@/lib/sessions/rows";

interface Props {
  /** The row being deleted; null keeps the dialog closed. */
  row: SessionRowData | null;
  /** What the list holds: a conversation of a channel, or a session of an agent. */
  kind: "conversation" | "session";
  pending: boolean;
  onCancel: () => void;
  onConfirm: (row: SessionRowData) => Promise<unknown>;
}

export function DeleteSessionDialog({ row, kind, pending, onCancel, onConfirm }: Props) {
  const { t } = useTranslation();
  // The title stays through the close animation, so the question does not go blank.
  const title = row?.title ?? "";
  return (
    <ConfirmDialog
      open={row !== null}
      onOpenChange={(open) => !open && onCancel()}
      title={t("sessions.delete.title", { title })}
      description={t(`sessions.delete.${kind}Body`)}
      confirmLabel={t(`sessions.delete.${kind}Confirm`)}
      pendingLabel={t("common.deleting")}
      errorTitle={t("sessions.delete.failed")}
      pending={pending}
      onConfirm={() => (row ? onConfirm(row) : undefined)}
    />
  );
}
