// src/components/custom-tools/DeleteGroupDialog.tsx — Delete group…: who loses its tools, what stays (the
// secret, the call history), and that turning it off is the way to stop it for a while.
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { agentTypeLabel } from "@/lib/agents/display";
import { useAgents } from "@/lib/hooks/useAgents";
import { useDeleteCustomToolGroup } from "@/lib/hooks/useCustomTools";

interface Props {
  group: CustomToolGroup;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeleted: () => void;
}

export function DeleteGroupDialog({ group, open, onOpenChange, onDeleted }: Props) {
  const { t } = useTranslation();
  const { data: agents } = useAgents();
  const del = useDeleteCustomToolGroup(group.name);
  const reached = (agents ?? []).filter((a) => group.scope === null || group.scope.includes(a.uid));
  const names = reached.map((a) => (a.type ? agentTypeLabel(a.type) : a.name));
  const who =
    names.length === 0
      ? t("customTools.deleteGroup.noAgents")
      : names.length === 1
        ? names[0]
        : `${names.slice(0, -1).join(", ")}${t("customTools.editor.and")}${names[names.length - 1]}`;
  const body = t("customTools.deleteGroup.body", { count: group.tools.length, agents: who });
  const secret = group.auth?.secret
    ? t("customTools.deleteGroup.secretStays", { secret: group.auth.secret })
    : t("customTools.deleteGroup.historyStays");

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) del.reset();
      }}
      title={t("customTools.group.deleteTitle", { name: group.name })}
      description={`${body} ${secret}`}
      confirmLabel={t("customTools.group.delete")}
      pendingLabel={t("common.deleting")}
      errorTitle={t("common.couldntDelete", { name: group.name })}
      pending={del.isPending}
      error={del.error}
      onConfirm={() =>
        del.mutate(undefined, {
          onSuccess: () => {
            onOpenChange(false);
            onDeleted();
          },
        })
      }
    >
      <p className="text-xs text-text-muted">{t("customTools.deleteGroup.undo")}</p>
    </ConfirmDialog>
  );
}
