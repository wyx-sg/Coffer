// frontend/src/components/agents/AgentUnmanagedSkillsBulkActions.tsx
// Bulk actions for the agent's unmanaged-skills table: adopt-into-master and
// delete over the selected rows. Adopt only touches eligible rows (valid
// SKILL.md and not a foreign symlink) — the same gate the per-row button
// enforces — and fans them out with allSettled via useBulkMutate. Delete is
// destructive and owns its own confirm dialog. Kept in its own file so
// AgentUnmanagedSkills.tsx stays small.
import { useState } from "react";
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
import { agentsApi, type UnmanagedSkillOut } from "@/lib/api/agents";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";

export function AgentUnmanagedSkillsBulkActions({
  agentName,
  rows,
  clear,
}: {
  agentName: string;
  rows: UnmanagedSkillOut[];
  clear: () => void;
}) {
  const { t } = useTranslation();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const invalidate = [["agents", agentName, "unmanaged-skills"], ["skills"], ["agents", agentName]];
  const adopt = useBulkMutate({ invalidate });
  const remove = useBulkMutate({ invalidate });

  const adoptable = rows.filter((s) => s.valid && !s.foreign_link);

  const adoptAll = async () => {
    await adopt.run(adoptable, (s) => agentsApi.adoptUnmanagedSkill(agentName, s.name, s.location));
    clear();
  };

  const deleteAll = async () => {
    await remove.run(rows, (s) => agentsApi.deleteUnmanagedSkill(agentName, s.name, s.location));
    setConfirmDelete(false);
    clear();
  };

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        disabled={adoptable.length === 0 || adopt.isPending}
        onClick={() => void adoptAll()}
      >
        {t("agents.skillsTab.adopt")}
      </Button>
      <Button
        size="sm"
        variant="outline"
        className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
        disabled={remove.isPending}
        onClick={() => setConfirmDelete(true)}
      >
        {t("common.bulk.delete")}
      </Button>

      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("common.bulk.delete")}</DialogTitle>
            <DialogDescription>
              {t("agents.skillsTab.bulkDeleteConfirm", { count: rows.length })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() => void deleteAll()}
            >
              {t("common.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
