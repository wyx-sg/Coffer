// frontend/src/components/skills/SkillsReadingPane.tsx
// The Skills page's right-hand pane: one of, in this order — what Check copies
// found (SkillCopiesPanel), the rows ticked in the library (SkillSelectionPane),
// the list's load error, the open skill (SkillDetailPane, loaded on first open
// because its Files tab pulls in the editor and the Markdown pipeline), a
// skill name that matches nothing, the first run while the library holds
// nothing of the user's own, or a prompt to choose a skill.
import { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";
import { Sparkles } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageFallback } from "@/components/PageFallback";
import type { SkillAddSource } from "@/components/skills/SkillAddDialog";
import { SkillCopiesPanel } from "@/components/skills/SkillCopiesPanel";
import { SkillFirstRun } from "@/components/skills/SkillFirstRun";
import { SkillOrphanPane } from "@/components/skills/SkillOrphanPane";
import { SkillSelectionPane } from "@/components/skills/SkillSelectionPane";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
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
  if (list.error) {
    return (
      <EmptyState
        tone="error"
        icon={Sparkles}
        title={t("skills.loadFailed")}
        description={translateApiError(t, list.error)}
        action={
          <Button variant="outline" onClick={() => void list.refetch()}>
            {t("common.retry")}
          </Button>
        }
      />
    );
  }
  if (list.isPending) return <PageFallback />;
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
    return (
      <EmptyState
        icon={Sparkles}
        title={t("skills.detail.notFound", { name: nameParam })}
        description={t("skills.choose.body")}
      />
    );
  }
  if (skills.every((s) => s.builtin)) {
    return <SkillFirstRun hasBuiltin={skills.length > 0} onAdd={props.onAdd} />;
  }
  return (
    <EmptyState
      icon={Sparkles}
      title={t("skills.choose.title")}
      description={t("skills.choose.body")}
    />
  );
}
