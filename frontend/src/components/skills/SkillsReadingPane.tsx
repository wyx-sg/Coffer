// frontend/src/components/skills/SkillsReadingPane.tsx
// The Skills page's right-hand pane: one of, in this order — what Check copies
// found (SkillCopiesPanel), the rows ticked in the library (SkillSelectionPane),
// nothing while the list loads or failed (its pane says why), the open skill
// (SkillDetailPane, loaded on first open because its Files tab pulls in the
// editor and the Markdown pipeline), a skill name that matches nothing, the
// first run while the library holds nothing of the user's own, or Nothing
// selected.
import { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";
import { Sparkle } from "lucide-react";

import { DetailNotFound } from "@/components/DetailNotFound";
import { NothingSelected } from "@/components/ListPaneStates";
import { PageFallback } from "@/components/PageFallback";
import type { SkillAddSource } from "@/components/skills/SkillAddDialog";
import { SkillCopiesPanel } from "@/components/skills/SkillCopiesPanel";
import { SkillFirstRun } from "@/components/skills/SkillFirstRun";
import { SkillOrphanPane } from "@/components/skills/SkillOrphanPane";
import { SkillSelectionPane } from "@/components/skills/SkillSelectionPane";
import type { SkillOut } from "@/lib/api/skills";
import type { SkillTab } from "@/lib/skills/tabs";

const SkillDetailPane = lazy(() =>
  import("@/components/skills/SkillDetailPane").then((m) => ({ default: m.SkillDetailPane })),
);

interface Props {
  list: { error: unknown; isPending: boolean; refetch: () => unknown };
  skills: SkillOut[];
  match: SkillOut | null;
  nameParam: string;
  /** A store folder no skill claims, open from `?orphan=`. */
  orphan: string | null;
  tab: SkillTab;
  onTabChange: (tab: string) => void;
  showCopies: boolean;
  onCloseCopies: () => void;
  selected: SkillOut[];
  onClearSelection: () => void;
  onAdd: (source: SkillAddSource) => void;
  onDeleted: () => void;
}

export function SkillsReadingPane(props: Props) {
  const { t } = useTranslation();
  const { list, skills, match, nameParam } = props;

  if (props.showCopies) return <SkillCopiesPanel onClose={props.onCloseCopies} />;
  if (props.selected.length > 0) {
    return (
      <SkillSelectionPane
        skills={props.selected}
        builtin={skills.filter((s) => s.builtin).map((s) => s.name)}
        onDone={props.onClearSelection}
      />
    );
  }
  // The list pane says why it is empty (loading, or the error block).
  if (list.error || list.isPending) return null;
  if (props.orphan) return <SkillOrphanPane name={props.orphan} />;
  if (match) {
    return (
      <Suspense fallback={<PageFallback />}>
        <SkillDetailPane
          skill={match}
          tab={props.tab}
          onTabChange={props.onTabChange}
          onDeleted={props.onDeleted}
        />
      </Suspense>
    );
  }
  if (nameParam) {
    return <DetailNotFound kind="skills" id={nameParam} backTo="/skills" icon={Sparkle} />;
  }
  if (skills.every((s) => s.builtin)) {
    return <SkillFirstRun hasBuiltin={skills.length > 0} onAdd={props.onAdd} />;
  }
  return (
    <NothingSelected
      icon={Sparkle}
      addLabel={t("skills.add")}
      onAdd={() => props.onAdd("folder")}
    />
  );
}
