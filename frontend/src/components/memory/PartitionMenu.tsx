// frontend/src/components/memory/PartitionMenu.tsx — the ⋯ menu on a partition's header.
//
// Reveal partition folder · Copy path · Delete partition…. Delete is offered
// only while the partition's repository is gone (spec memory "Report
// unresolvable partitions"): any other partition comes back on the next
// Update memory. A successful delete leaves for the partitions list.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DeletePartitionDialog } from "@/components/memory/DeletePartitionDialog";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import { useToast } from "@/components/ui/toast";
import type { PartitionOut } from "@/lib/api/memoryTypes";
import { useFsActions } from "@/lib/fsActions";
import { usePartitionFiles } from "@/lib/hooks/useMemory";
import { displayName } from "@/lib/resourceTitle";

interface Props {
  partition: PartitionOut;
}

export function PartitionMenu({ partition }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const navigate = useNavigate();
  const { reveal } = useFsActions();
  const files = usePartitionFiles(partition.uid);
  const [deleting, setDeleting] = useState<PartitionOut | null>(null);
  const folder = files.data?.abs_path ?? null;

  const actions: MenuAction[] = [
    {
      key: "reveal",
      label: t("memory.detail.menu.reveal"),
      disabled: folder === null,
      onSelect: () => {
        if (folder) void reveal(folder).catch(() => toast.error(t("fileActions.revealFailed")));
      },
    },
    {
      key: "copy",
      label: t("memory.detail.menu.copyPath"),
      disabled: folder === null,
      onSelect: () => {
        if (!folder) return;
        void navigator.clipboard
          ?.writeText(folder)
          .then(() => toast.success(t("common.copied")))
          .catch(() => undefined);
      },
    },
  ];
  if (partition.unresolvable) {
    actions.push({
      key: "delete",
      label: t("memory.detail.menu.delete"),
      destructive: true,
      separated: true,
      onSelect: () => setDeleting(partition),
    });
  }

  return (
    <>
      <ActionMenu
        label={t("memory.detail.menu.label", { name: displayName(partition) })}
        actions={actions}
      />
      <DeletePartitionDialog
        partition={deleting}
        onClose={() => setDeleting(null)}
        onDeleted={() => navigate("/memory")}
      />
    </>
  );
}
