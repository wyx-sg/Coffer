// frontend/src/components/skills/SkillsBulkBar.tsx
// The library's selection bar, at the top of the column while rows are ticked
// (canvas 4.3.29) in the place of the filters — the same bar the MCP servers
// list shows (ListSelectionBar): select-all, how many are selected, Clear, and
// here the selection's reach (the same three-state choice every row carries,
// written to each) and Delete. The built-in skill never reaches here: it has
// no checkbox and select-all skips it.
import { useTranslation } from "react-i18next";

import { ListSelectionBar } from "@/components/ListSelectionBar";
import { BulkReachActions } from "@/components/reach/BulkReachActions";
import { SkillBulkDelete } from "@/components/skills/SkillBulkDelete";
import { skillsKey } from "@/lib/api/queryKeys";
import type { SkillOut } from "@/lib/api/skills";

interface Props {
  skills: SkillOut[];
  /** Every listed skill the filters show (built-in excluded) is ticked. */
  allChecked: boolean;
  onToggleAll: (on: boolean) => void;
  /** Clears the selection once a bulk write has settled (or on Clear). */
  onDone: () => void;
}

export function SkillsBulkBar({ skills, allChecked, onToggleAll, onDone }: Props) {
  const { t } = useTranslation();
  return (
    <ListSelectionBar
      label={t("skills.bulk.label")}
      selectAllLabel={t("skills.selectAll")}
      count={skills.length}
      allChecked={allChecked}
      onToggleAll={onToggleAll}
      onClear={onDone}
    >
      <BulkReachActions
        rows={skills.map((s) => ({ kind: "skill", uid: s.uid }))}
        invalidate={[skillsKey]}
        onDone={onDone}
      />
      <SkillBulkDelete skills={skills} onDone={onDone} label={t("common.delete")} />
    </ListSelectionBar>
  );
}
