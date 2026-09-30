// frontend/src/components/skills/SkillsBulkBar.tsx
// The library's selection bar: how many rows are selected, the selection's
// reach (the same three-state choice every row carries, written to each) and
// Delete them all behind one confirmation. The built-in skill never reaches
// here — its row has no checkbox, because this bar's one destructive action
// would have to refuse it.
import { useTranslation } from "react-i18next";

import { BulkReachActions } from "@/components/reach/BulkReachActions";
import { BulkDeleteButton } from "@/components/table/BulkDeleteButton";
import { Button } from "@/components/ui/button";
import { skillsKey } from "@/lib/api/queryKeys";
import { skillsApi, type SkillOut } from "@/lib/api/skills";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";

interface Props {
  skills: SkillOut[];
  /** Clears the selection once a bulk write has settled (or on Clear). */
  onDone: () => void;
}

export function SkillsBulkBar({ skills, onDone }: Props) {
  const { t } = useTranslation();
  // allSettled fan-out: one failed remove never aborts the rest; the summary
  // toast reports the outcome and the selection always clears (never stuck).
  const bulk = useBulkMutate({ invalidate: [skillsKey] });

  return (
    <div
      role="region"
      aria-label={t("skills.bulk.label")}
      className="flex flex-wrap items-center gap-2 border-t border-border-subtle bg-surface-raised px-3 py-2"
    >
      <span className="text-xs font-label text-text">
        {t("common.bulk.selected", { count: skills.length })}
      </span>
      <Button variant="ghost" size="sm" onClick={onDone}>
        {t("common.clear")}
      </Button>
      <span className="ml-auto inline-flex flex-wrap items-center gap-2">
        <BulkReachActions
          rows={skills.map((s) => ({ kind: "skill", uid: s.uid }))}
          invalidate={[skillsKey]}
          onDone={onDone}
        />
        <BulkDeleteButton
          title={t("skills.removeConfirmTitle", { name: skills.map((s) => s.name).join(", ") })}
          description={t("skills.removeConfirmBody")}
          pending={bulk.isPending}
          onConfirm={async () => {
            await bulk.run(skills, (s) => skillsApi.remove(s.uid));
            onDone();
          }}
        />
      </span>
    </div>
  );
}
