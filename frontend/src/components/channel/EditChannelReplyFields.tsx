// frontend/src/components/channel/EditChannelReplyFields.tsx
// The step-lines switch of a channel's Settings tab: list the last steps under
// the live status line, or keep only the status line. Shown only for a channel
// whose platform has a live status line (see showsStepLines).
import { useId } from "react";
import { useTranslation } from "react-i18next";

import { SettingRow } from "@/components/settings/SettingsLayout";
import { Switch } from "@/components/ui/switch";

export function EditChannelReplyFields({
  showSteps,
  onChange,
}: {
  showSteps: boolean;
  onChange: (showSteps: boolean) => void;
}) {
  const { t } = useTranslation();
  const stepsId = `${useId()}-steps`;
  const stepsHintId = `${stepsId}-hint`;

  return (
    <SettingRow
      label={t("channels.edit.replies.showSteps")}
      labelFor={stepsId}
      description={t("channels.edit.replies.showStepsHint")}
      descriptionId={stepsHintId}
    >
      <Switch
        id={stepsId}
        aria-describedby={stepsHintId}
        checked={showSteps}
        onCheckedChange={onChange}
      />
    </SettingRow>
  );
}
