// frontend/src/components/skills/SkillFileConflict.tsx
// "SKILL.md changed on both sides" (canvas 4.3.14): the 1060 two-way choice
// after a save was refused because the file changed on disk. Keep my edit saves
// the text over the file — naming the fingerprint of what was just read, so it
// is still a compare-and-swap — Take the version on disk reloads the file and
// drops the edit. The diff is the change the choice makes to the side that is
// not kept; nothing is written until the primary is pressed.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { FileDiff } from "@/components/change-preview/FileDiff";
import { SkillChoiceDialog } from "@/components/skills/SkillChoiceDialog";
import { textChangeItem } from "@/components/skills/textDiff";
import { DialogErrorBanner } from "@/components/ui/confirm-dialog";
import { translateApiError } from "@/lib/api/errors";
import { useWriteSkillFile } from "@/lib/hooks/useSkills";

type Keep = "mine" | "disk";

interface Props {
  uid: string;
  owner: string;
  path: string;
  /** What the person typed. */
  mine: string;
  /** What the disk says now, with the fingerprint a save over it must name. */
  disk: { text: string; fingerprint: string };
  onClose: () => void;
  onTakeDisk: () => void;
  onSavedOver: () => void;
}

export function SkillFileConflict({
  uid,
  owner,
  path,
  mine,
  disk,
  onClose,
  onTakeDisk,
  onSavedOver,
}: Props) {
  const { t } = useTranslation();
  const write = useWriteSkillFile(uid);
  const [keep, setKeep] = useState<Keep>("mine");
  const name = path.split("/").pop() ?? path;
  const item = useMemo(
    () =>
      keep === "mine"
        ? textChangeItem("file", `${owner}/${path}`, disk.text, mine)
        : textChangeItem("file", `${owner}/${path}`, mine, disk.text),
    [keep, owner, path, disk.text, mine],
  );

  const confirm = () => {
    if (keep === "disk") return onTakeDisk();
    write.mutate(
      { path, content: mine, expected_fingerprint: disk.fingerprint },
      { onSuccess: onSavedOver },
    );
  };

  return (
    <SkillChoiceDialog<Keep>
      open
      onOpenChange={(open) => !open && onClose()}
      title={t("skills.fileConflict.title", { file: name })}
      subtitle={t("skills.fileConflict.subtitle")}
      groupLabel={t("skills.fileConflict.choose")}
      choices={[
        {
          value: "mine",
          title: t("skills.fileConflict.keepMine"),
          help: t("skills.fileConflict.keepMineHelp"),
        },
        {
          value: "disk",
          title: t("skills.fileConflict.takeDisk"),
          help: t("skills.fileConflict.takeDiskHelp"),
        },
      ]}
      value={keep}
      onChange={setKeep}
      confirmLabel={
        keep === "mine" ? t("skills.fileConflict.saveMine") : t("skills.fileConflict.useDisk")
      }
      onConfirm={confirm}
      pending={write.isPending}
      error={
        write.error ? (
          <DialogErrorBanner
            title={t("skills.fileConflict.failed", { file: name })}
            message={translateApiError(t, write.error)}
          />
        ) : null
      }
    >
      <FileDiff item={item} />
      <p className="text-xs text-text-muted">
        {t(keep === "mine" ? "skills.fileConflict.captionMine" : "skills.fileConflict.captionDisk")}
      </p>
    </SkillChoiceDialog>
  );
}
