// frontend/src/components/skills/SkillsBulkBar.tsx
// The library's selection bar, at the top of the column while rows are ticked
// (canvas 4.3.29) in the place of the filters — the same bar the MCP servers
// list shows (ListSelectionBar): how many of the listed are selected, Clear, and
// here the selection's reach (the same three-state choice every row carries,
// written to each), Check with an agent (one prompt for all of them) and Delete. The built-in skill never reaches here: it has
// no checkbox.
import { useTranslation } from "react-i18next";

import { ListSelectionBar } from "@/components/ListSelectionBar";
import { BulkReachActions } from "@/components/reach/BulkReachActions";
import { SkillReviewHandoff } from "@/components/skills/SkillReviewHandoff";
import { SkillBulkDelete } from "@/components/skills/SkillBulkDelete";
import { skillsKey } from "@/lib/api/queryKeys";
import type { SkillOut } from "@/lib/api/skills";

interface Props {
  skills: SkillOut[];
  /** How many skills the filters show (built-in excluded). */
  total: number;
  /** Clears the selection once a bulk write has settled (or on Clear). */
  onDone: () => void;
}

export function SkillsBulkBar({ skills, total, onDone }: Props) {
  const { t } = useTranslation();
  return (
    <ListSelectionBar
      label={t("skills.bulk.label")}
      count={skills.length}
      total={total}
      onClear={onDone}
    >
      <BulkReachActions
        rows={skills.map((s) => ({
          kind: "skill",
          uid: s.uid,
          name: s.name,
          enabled: s.enabled,
          scope: s.scope,
        }))}
        invalidate={[skillsKey]}
        onDone={onDone}
      />
      <SkillReviewHandoff uids={skills.map((s) => s.uid)} label={t("skills.bulk.review")} />
      <SkillBulkDelete skills={skills} onDone={onDone} label={t("common.delete")} />
    </ListSelectionBar>
  );
}
