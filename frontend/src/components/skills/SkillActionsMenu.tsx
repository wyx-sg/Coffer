// frontend/src/components/skills/SkillActionsMenu.tsx
// The open skill's "⋯" menu (canvas 4.3 page note): Open in editor · Reveal in
// Finder · Copy master path · Check agents' copies · Turn off (removes it from
// every agent and keeps who was chosen) · Delete…. The name is fixed and is the
// heading, so there is no rename. Coffer's built-in skill keeps the menu but
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
import { useDisableResource, useEnableResource } from "@/lib/hooks/useResourceMutations";

interface Props {
  skill: SkillOut;
  onCheckCopies: () => void;
  onDeleted: () => void;
}

export function SkillActionsMenu({ skill, onCheckCopies, onDeleted }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const editor = usePreferredEditor();
  const fs = useFsActions();
  const enable = useEnableResource();
  const disable = useDisableResource();
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
      key: "check",
      label: t("skills.menu.checkCopies"),
      onSelect: onCheckCopies,
      separated: true,
    },
    skill.enabled
      ? {
          key: "off",
          label: t("skills.menu.turnOff"),
          onSelect: () => disable.mutate({ kind: "skill", uid: skill.uid }),
        }
      : {
          key: "on",
          label: t("skills.menu.turnOn"),
          onSelect: () => enable.mutate({ kind: "skill", uid: skill.uid }),
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
