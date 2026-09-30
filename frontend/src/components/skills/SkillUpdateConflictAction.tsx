// src/components/skills/SkillUpdateConflictAction.tsx
// The confirm button of the update conflict's chosen card, in the dialog's
// footer: Keep my edits, Take the update (confirmed by the dialog's own
// discard confirmation), or — after the agent merged the update into the
// edits — I merged it, confirmed here: Coffer pins the skill to the update's
// commit and leaves the master folder's files as they are (spec skill-manager
// "Record an update merged into local edits").
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { SkillUpdatePreview } from "@/lib/api/skills";
import { useMarkSkillMerged } from "@/lib/hooks/useSkills";
import type { ConflictChoice } from "./SkillUpdateConflict";
import { shortCommit } from "./skillSourceHelpers";

interface Props {
  uid: string;
  name: string;
  preview: SkillUpdatePreview;
  choice: ConflictChoice | null;
  busy: boolean;
  onKeep: () => void;
  onTake: () => void;
  /** After the merge is recorded. */
  onMerged: () => void;
}

export function SkillUpdateConflictAction({
  uid,
  name,
  preview,
  choice,
  busy,
  onKeep,
  onTake,
  onMerged,
}: Props) {
  const { t } = useTranslation();
  const merged = useMarkSkillMerged();
  const [confirming, setConfirming] = useState(false);
  const label =
    choice === "merge"
      ? t("skillSources.conflict.merged")
      : choice === "keep"
        ? t("skillSources.conflict.keep")
        : t("skillSources.conflict.take");
  const act = () =>
    choice === "merge" ? setConfirming(true) : choice === "keep" ? onKeep() : onTake();
  return (
    <>
      <Button type="button" disabled={!choice || busy || merged.isPending} onClick={act}>
        {label}
      </Button>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t("skillSources.conflict.mergedTitle")}
        description={t("skillSources.conflict.mergedBody", {
          name,
          to: shortCommit(preview.to_commit),
        })}
        confirmLabel={t("skillSources.conflict.merged")}
        onConfirm={async () => {
          await merged.mutateAsync({ uid, commit: preview.to_commit });
          onMerged();
        }}
      />
    </>
  );
}
