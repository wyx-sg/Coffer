// frontend/src/components/skills/SkillMissingMaster.tsx
// The Files tab of a skill whose master folder is gone (canvas 4.3.04): an
// empty state saying why there are no files. The two ways forward (the hand-off
// that looks for a copy, and Delete skill…) are in the banner above the tabs
// (SkillMasterBanner), not here.
import { useTranslation } from "react-i18next";
import { FolderX } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";

export function SkillMissingMaster() {
  const { t } = useTranslation();
  return (
    <EmptyState
      icon={FolderX}
      title={t("skills.missing.emptyTitle")}
      description={t("skills.missing.emptyBody")}
    />
  );
}
