// src/components/agents/skills/DeleteOwnSkillDialog.tsx — confirm deleting a skill folder Coffer doesn't manage (board 2.1.21).
//
// The folder is the agent's own and not in Coffer's library, so nothing can
// restore it: the dialog names the folder and how many files go with it (read
// from the folder's own file tree) before anything is deleted.
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { SkillFileNode } from "@/lib/api/skills";
import { useUnmanagedSkillFiles } from "@/lib/hooks/useUnmanagedSkill";
import type { OwnSkillRow } from "./skillRows";

interface Props {
  agentUid: string;
  target: OwnSkillRow | null;
  pending: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (row: OwnSkillRow) => void;
}

function countFiles(node: SkillFileNode | undefined): number | undefined {
  if (!node) return undefined;
  if (node.type === "file") return 1;
  return node.children.reduce((sum, child) => sum + (countFiles(child) ?? 0), 0);
}

export function DeleteOwnSkillDialog({
  agentUid,
  target,
  pending,
  onOpenChange,
  onConfirm,
}: Props) {
  const { t } = useTranslation();
  const files = useUnmanagedSkillFiles(
    target ? agentUid : "",
    target?.item.location ?? "",
    target?.name ?? "",
  );
  const count = countFiles(files.data);
  const path = target ? abbreviateHomePath(target.item.path) : "";
  return (
    <ConfirmDialog
      open={target !== null}
      onOpenChange={onOpenChange}
      title={t("agents.skillsTab.deleteTitle", { name: target?.name ?? "" })}
      description={
        count === undefined
          ? t("agents.skillsTab.deleteBodyNoCount", { path })
          : t("agents.skillsTab.deleteBody", { path, count })
      }
      confirmLabel={t("common.delete")}
      pending={pending}
      onConfirm={() => {
        if (target) onConfirm(target);
      }}
    />
  );
}
