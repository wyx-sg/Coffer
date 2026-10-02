// frontend/src/components/skills/SkillActionsMenu.tsx
// The open skill's "⋯" menu (canvas 4.3 page note): Open in editor · Reveal in
// Finder · Copy master path · Delete…. Turning it on or off is the reach
// button's and Check copies is the Delivery tab's and the library's, so the
// menu does not repeat them. The name is fixed and is the heading, so there is
// no rename. Coffer's built-in skill keeps the menu but
// Delete is disabled — Coffer writes it itself; the built-in banner says to
// turn it off instead.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { SkillDeleteDialog } from "@/components/skills/SkillDeleteDialog";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import { useToast } from "@/components/ui/toast";
import type { SkillOut } from "@/lib/api/skills";
import { useFsActions } from "@/lib/fsActions";
import { usePreferredEditor } from "@/lib/preferences";

interface Props {
  skill: SkillOut;
  onDeleted: () => void;
}

export function SkillActionsMenu({ skill, onDeleted }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const editor = usePreferredEditor();
  const fs = useFsActions();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const path = skill.master_path;

  const actions: MenuAction[] = [
    {
      key: "open",
      label: t("fileActions.openInEditor"),
      onSelect: () =>
        void fs.open(path, editor).catch(() => toast.error(t("fileActions.openFailed"))),
    },
    {
      key: "reveal",
      label: t("fileActions.reveal"),
      onSelect: () => void fs.reveal(path).catch(() => toast.error(t("fileActions.revealFailed"))),
    },
    {
      key: "copy",
      label: t("skills.menu.copyPath"),
      onSelect: () =>
        void navigator.clipboard.writeText(path).then(
          () => toast.success(t("common.copied")),
          () => toast.error(t("skills.menu.copyFailed")),
        ),
    },
    {
      key: "delete",
      label: t("skills.menu.delete"),
      destructive: true,
      disabled: skill.builtin,
      separated: true,
      onSelect: () => setDeleteOpen(true),
    },
  ];

  return (
    <>
      <ActionMenu label={t("skills.menu.label", { name: skill.name })} actions={actions} />
      {skill.builtin ? null : (
        <SkillDeleteDialog
          skill={skill}
          open={deleteOpen}
          onOpenChange={setDeleteOpen}
          onDeleted={onDeleted}
        />
      )}
    </>
  );
}
