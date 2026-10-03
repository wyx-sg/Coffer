// src/components/custom-tools/GroupReachField.tsx — "Available to" in the new-group forms: the standard
// reach control (label above, one line of help below), held as a draft until the group is created.
import { useTranslation } from "react-i18next";

import { ReachControl } from "@/components/reach/ReachControl";
import { Label } from "@/components/ui/label";
import { EVERY_AGENT, type ReachDraft } from "./addFlow";

interface Props {
  value: ReachDraft;
  onChange: (value: ReachDraft) => void;
  /** The line under the control. */
  help: string;
  busy?: boolean;
}

export function GroupReachField({ value, onChange, help, busy }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-start gap-1.5">
      <Label>{t("customTools.fields.availableTo")}</Label>
      <ReachControl
        mode={value.mode}
        initialScope={value.scope}
        busy={busy}
        ariaLabel={t("customTools.fields.availableTo")}
        testId="group-reach"
        onDisabled={() => onChange({ mode: "disabled", scope: value.scope })}
        onEverywhere={() => onChange(EVERY_AGENT)}
        onRestricted={(scope) => onChange({ mode: "restricted", scope })}
      />
      <p className="text-xs text-text-muted">{help}</p>
    </div>
  );
}
