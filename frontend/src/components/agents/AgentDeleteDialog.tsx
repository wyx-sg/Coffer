// frontend/src/components/agents/AgentDeleteDialog.tsx — spec 004-agent-registry.
// Delete-confirmation dialog for AgentDetailPage. Extracted to keep that
// page under the file-size limit; owns the useRemoveAgent mutation itself so
// the page only wires the open state and the post-delete navigation.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useRemoveAgent } from "@/lib/hooks/useAgents";

export function AgentDeleteDialog({
  name,
  open,
  onOpenChange,
  onDeleted,
}: {
  name: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeleted: () => void;
}) {
  const { t } = useTranslation();
  const remove = useRemoveAgent();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("agents.removeConfirm", { name })}</DialogTitle>
          <DialogDescription>{t("agents.removeConfirmBody")}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            variant="destructive"
            disabled={remove.isPending}
            onClick={() =>
              remove.mutate(name, {
                onSuccess: () => {
                  onOpenChange(false);
                  onDeleted();
                },
              })
            }
          >
            {remove.isPending ? t("common.deleting") : t("common.delete")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
