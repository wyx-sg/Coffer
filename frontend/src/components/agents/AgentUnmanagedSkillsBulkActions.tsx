// frontend/src/components/agents/AgentUnmanagedSkillsBulkActions.tsx
// Bulk actions for the agent's unmanaged-skills table: adopt-into-master and
// delete over the selected rows. Adopt only touches eligible rows (valid
// SKILL.md and not a foreign symlink) — the same gate the per-row button
// enforces — and fans them out with allSettled via useBulkMutate. Delete is
// destructive and owns its own confirm dialog. Kept in its own file so
// AgentUnmanagedSkills.tsx stays small.
import { useTranslation } from "react-i18next";
import { Import } from "lucide-react";

import { BulkDeleteButton } from "@/components/table/BulkDeleteButton";
import { TableActionButton } from "@/components/table/TableActionButton";
import { agentsApi, type UnmanagedSkillOut } from "@/lib/api/agents";
import { agentKey, agentUnmanagedSkillsKey, skillsKey } from "@/lib/api/queryKeys";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";

export function AgentUnmanagedSkillsBulkActions({
  agentUid,
  rows,
  clear,
}: {
  agentUid: string;
  rows: UnmanagedSkillOut[];
  clear: () => void;
}) {
  const { t } = useTranslation();
  const invalidate = [agentUnmanagedSkillsKey(agentUid), skillsKey, agentKey(agentUid)];
  const adopt = useBulkMutate({ invalidate });
  const remove = useBulkMutate({ invalidate });

  const adoptable = rows.filter((s) => s.valid && !s.foreign_link);

  const adoptAll = async () => {
    await adopt.run(adoptable, (s) => agentsApi.adoptUnmanagedSkill(agentUid, s.name, s.location));
    clear();
  };

  const deleteAll = async () => {
    await remove.run(rows, (s) => agentsApi.deleteUnmanagedSkill(agentUid, s.name, s.location));
    clear();
  };

  return (
    <>
      <TableActionButton
        icon={Import}
        label={t("agents.skillsTab.adopt")}
        disabled={adoptable.length === 0 || adopt.isPending}
        onClick={() => void adoptAll()}
      />
      <BulkDeleteButton
        title={t("common.bulk.delete")}
        description={t("agents.skillsTab.bulkDeleteConfirm", { count: rows.length })}
        pending={remove.isPending}
        onConfirm={deleteAll}
      />
    </>
  );
}
