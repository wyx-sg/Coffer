// frontend/src/components/skills/SkillsBulkBar.tsx
// The library's selection bar, under the filter while rows are ticked (canvas
// 4.3.29): how many are selected, their reach (the same three-state choice
// every row carries, written to each), Delete, and × to clear the selection.
// The built-in skill never reaches here — its checkbox is disabled, because
// the bar's one destructive action would have to refuse it.
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";

import { BulkReachActions } from "@/components/reach/BulkReachActions";
import { SkillBulkDelete } from "@/components/skills/SkillBulkDelete";
import { Button } from "@/components/ui/button";
import { skillsKey } from "@/lib/api/queryKeys";
import type { SkillOut } from "@/lib/api/skills";

interface Props {
  skills: SkillOut[];
  /** Clears the selection once a bulk write has settled (or on ×). */
  onDone: () => void;
}

export function SkillsBulkBar({ skills, onDone }: Props) {
  const { t } = useTranslation();
  return (
    <div
      role="region"
      aria-label={t("skills.bulk.label")}
      className="flex flex-wrap items-center gap-2 rounded-lg bg-surface-sunken py-1.5 pl-3 pr-1.5"
    >
      <span className="mr-auto text-xs font-label text-text">
        {t("common.bulk.selected", { count: skills.length })}
      </span>
      <BulkReachActions
        rows={skills.map((s) => ({ kind: "skill", uid: s.uid }))}
        invalidate={[skillsKey]}
        onDone={onDone}
      />
      <SkillBulkDelete skills={skills} onDone={onDone} label={t("common.delete")} />
      <Button variant="ghost" size="icon-sm" aria-label={t("common.clear")} onClick={onDone}>
        <X aria-hidden />
      </Button>
    </div>
  );
}
