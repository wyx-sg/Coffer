// frontend/src/components/skills/SkillSelectionPane.tsx
// The reading pane while rows are ticked in the library (canvas 4.3.29): how
// many are selected and which, a pointer to the bar above the list (where
// Reach and Delete live — the pane does not repeat them) and Check copies of
// N skills. Coffer's built-in skill has no checkbox, and the pane says so by
// name.
import { useTranslation } from "react-i18next";
import { RefreshCw, Sparkle } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import type { SkillOut } from "@/lib/api/skills";
import { joinNames } from "@/lib/skills/names";

interface Props {
  skills: SkillOut[];
  /** Names of the built-in skills, which can't be selected. */
  builtin: string[];
  onCheckCopies: () => void;
}

export function SkillSelectionPane({ skills, builtin, onCheckCopies }: Props) {
  const { t, i18n } = useTranslation();
  const names = joinNames(
    skills.map((s) => s.name),
    i18n.language,
  );
  const body = t("skills.selection.body", { count: skills.length, names });
  const description =
    builtin.length > 0
      ? `${body}; ${t("skills.selection.builtin", { names: joinNames(builtin, i18n.language) })}.`
      : `${body}.`;

  return (
    <EmptyState
      icon={Sparkle}
      title={t("skills.selection.title", { count: skills.length })}
      description={description}
      action={
        <Button variant="outline" onClick={onCheckCopies}>
          <RefreshCw aria-hidden /> {t("skills.selection.checkCopies", { count: skills.length })}
        </Button>
      }
    />
  );
}
