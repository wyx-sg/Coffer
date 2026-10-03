// frontend/src/components/skills/SkillSelectionPane.tsx
// The reading pane while rows are ticked in the library (canvas 4.3.29): how
// many are selected and which, Set reach… (the one reach choice, written to
// every selected skill) and Delete N skills…. Coffer's built-in skill has no
// checkbox, and the pane says so by name.
import { useTranslation } from "react-i18next";
import { Sparkle } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { BulkReachActions } from "@/components/reach/BulkReachActions";
import { SkillBulkDelete } from "@/components/skills/SkillBulkDelete";
import { skillsKey } from "@/lib/api/queryKeys";
import type { SkillOut } from "@/lib/api/skills";
import { joinNames } from "@/lib/skills/names";

interface Props {
  skills: SkillOut[];
  /** Names of the built-in skills, which can't be selected. */
  builtin: string[];
  onDone: () => void;
}

export function SkillSelectionPane({ skills, builtin, onDone }: Props) {
  const { t, i18n } = useTranslation();
  const names = joinNames(
    skills.map((s) => s.name),
    i18n.language,
  );
  const description = [
    t("skills.selection.body", { names }),
    builtin.length > 0
      ? t("skills.selection.builtin", { names: joinNames(builtin, i18n.language) })
      : null,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <EmptyState
      icon={Sparkle}
      title={t("skills.selection.title", { count: skills.length })}
      description={description}
      action={
        <div className="flex flex-wrap items-center justify-center gap-2">
          <BulkReachActions
            rows={skills.map((s) => ({ kind: "skill", uid: s.uid }))}
            invalidate={[skillsKey]}
            onDone={onDone}
          />
          <SkillBulkDelete
            skills={skills}
            onDone={onDone}
            label={t("skills.selection.delete", { count: skills.length })}
          />
        </div>
      }
    />
  );
}
