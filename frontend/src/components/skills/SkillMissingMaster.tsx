// frontend/src/components/skills/SkillMissingMaster.tsx
// The Files tab of a skill whose master folder is gone (canvas 4.3.04): an
// empty state saying why there are no files and where to look — History keeps
// every version. The two ways forward (Restore from History, Delete skill…)
// are in the banner above the tabs (SkillMasterBanner), not here.
import { useTranslation } from "react-i18next";
import { FolderX } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";

interface Props {
  onOpenHistory: () => void;
}

export function SkillMissingMaster({ onOpenHistory }: Props) {
  const { t } = useTranslation();
  return (
    <EmptyState
      icon={FolderX}
      title={t("skills.missing.emptyTitle")}
      description={t("skills.missing.emptyBody")}
      action={
        <Button variant="outline" onClick={onOpenHistory}>
          {t("skills.missing.openHistory")}
        </Button>
      }
    />
  );
}
