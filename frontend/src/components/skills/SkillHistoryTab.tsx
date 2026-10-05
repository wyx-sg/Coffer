// frontend/src/components/skills/SkillHistoryTab.tsx
//
// A skill's History (spec skill-manager "Manage skills on REST and on the
// Skills page"; spec web-ui "Show a vault file's history on a History tab"):
// the versions of its master folder `skills/<name>/` in the vault, each with
// who wrote it and when, the chosen one's diff file by file, and Restore this
// version…, which puts the whole folder back as a new version. Coffer's own
// skill is rebuilt from the running build at every start and is not in the
// vault, so it has no history here.
import { useTranslation } from "react-i18next";
import { History } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { VaultHistoryView } from "@/components/history/VaultHistoryView";
import type { SkillOut } from "@/lib/api/skills";

export function SkillHistoryTab({ skill }: { skill: SkillOut }) {
  const { t } = useTranslation();
  if (skill.builtin) {
    return (
      <EmptyState
        icon={History}
        title={t("skills.history.builtinTitle")}
        description={t("skills.history.builtinBody")}
      />
    );
  }
  return <VaultHistoryView path={`skills/${skill.name}/`} storageKey="skill-history" />;
}
