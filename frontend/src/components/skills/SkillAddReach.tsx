// frontend/src/components/skills/SkillAddReach.tsx
// "Available to" in the Add skill dialog (canvas 4.3.32): the one reach
// control (Foundations 0.7.02), held as a draft until the skill is added —
// All agents unless the reader narrows it — with a line saying what it is.
// The dialog writes the draft onto each added skill.
import { useTranslation } from "react-i18next";

import { ReachControl } from "@/components/reach/ReachControl";
import { Label } from "@/components/ui/label";
import { EVERY_AGENT, type SkillReachDraft } from "@/lib/skills/reach";

interface Props {
  value: SkillReachDraft;
  onChange: (value: SkillReachDraft) => void;
  /** Greyed out while the skill is being added. */
  busy?: boolean;
}

export function SkillAddReach({ value, onChange, busy }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-start gap-1.5">
      <Label>{t("skills.addReach.availableTo")}</Label>
      <ReachControl
        mode={value.mode}
        initialScope={value.scope}
        busy={busy}
        ariaLabel={t("skills.addReach.availableTo")}
        testId="skill-add-reach"
        onDisabled={() => onChange({ mode: "disabled", scope: value.scope })}
        onEverywhere={() => onChange(EVERY_AGENT)}
        onRestricted={(scope) => onChange({ mode: "restricted", scope })}
      />
      <p className="text-xs leading-[1.45] text-text-muted">{t("skills.addReach.help")}</p>
    </div>
  );
}
