// src/components/skills/SkillUpdateConflict.tsx
// An update that meets local edits (canvas 4.3.19): "changed on both sides",
// then two confirmed choices — Keep my edits (stays pinned; Coffer says so
// again at a newer update) or Take the update (your edits are replaced) — over
// the files you edited here. The dialog's footer carries the confirm button
// for the chosen card; Compare opens the three versions of a file.
//
// Spec skill-manager "Update a Git-imported skill from its source": a conflict
// offers Keep mine, Take theirs and Compare instead of a plain preview.
import { useTranslation } from "react-i18next";

import { SkillChoiceCards } from "@/components/skills/SkillChoiceCards";
import type { SkillUpdatePreview } from "@/lib/api/skills";
import { shortCommit } from "./skillSourceHelpers";
import { SkillUpdateDiff } from "./SkillUpdateDiff";

export type ConflictChoice = "keep" | "take";

interface Props {
  name: string;
  preview: SkillUpdatePreview;
  choice: ConflictChoice | null;
  onChoose: (choice: ConflictChoice) => void;
}

export function SkillUpdateConflict({ name, preview, choice, onChoose }: Props) {
  const { t } = useTranslation();
  const pinned = shortCommit(preview.from_commit);
  const to = shortCommit(preview.to_commit);
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <p className="text-xs text-text-muted">{t("skillSources.conflict.body", { pinned, to })}</p>
      <SkillChoiceCards<ConflictChoice>
        label={t("skillSources.conflict.title", { name })}
        value={choice}
        onChange={onChoose}
        choices={[
          {
            value: "keep",
            title: t("skillSources.conflict.keep"),
            help: t("skillSources.conflict.keepHelp", { pinned }),
          },
          {
            value: "take",
            title: t("skillSources.conflict.take"),
            help: t("skillSources.conflict.takeHelp", { to }),
          },
        ]}
      />
      <div className="flex flex-col gap-3" aria-label={t("skillSources.conflict.localEditsLabel")}>
        {preview.local_changes.map((change) => (
          <SkillUpdateDiff key={change.path} change={change} />
        ))}
      </div>
    </div>
  );
}
