// frontend/src/components/skills/SkillAddReach.tsx
// "Available to" in the Add skill dialog (canvas 4.3.33): the one reach
// control, held as a draft until the skill is added — every agent unless the
// reader narrows it — with the count beside it and a reminder that reach can
// change any time. The dialog writes the draft onto each added skill.
import { useTranslation } from "react-i18next";

import { ReachControl } from "@/components/reach/ReachControl";
import { Label } from "@/components/ui/label";
import { useAgents } from "@/lib/hooks/useAgents";
import { EVERY_AGENT, type SkillReachDraft } from "@/lib/skills/reach";

interface Props {
  value: SkillReachDraft;
  onChange: (value: SkillReachDraft) => void;
}

export function SkillAddReach({ value, onChange }: Props) {
  const { t } = useTranslation();
  const { data: agents = [] } = useAgents();
  const total = agents.length;
  const count =
    value.mode === "disabled"
      ? 0
      : value.mode === "everywhere"
        ? total
        : (value.scope?.agents ?? []).filter((uid) => agents.some((a) => a.uid === uid)).length;
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{t("skills.addReach.availableTo")}</Label>
      <div className="flex flex-wrap items-center gap-2">
        <ReachControl
          mode={value.mode}
          initialScope={value.scope}
          ariaLabel={t("skills.addReach.availableTo")}
          testId="skill-add-reach"
          onDisabled={() => onChange({ mode: "disabled", scope: value.scope })}
          onEverywhere={() => onChange(EVERY_AGENT)}
          onRestricted={(scope) => onChange({ mode: "restricted", scope })}
        />
        <span className="text-xs text-text-muted">
          {t("skills.addReach.availableHint", { count, total })}
        </span>
      </div>
    </div>
  );
}
