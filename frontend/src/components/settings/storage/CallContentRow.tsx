// src/components/settings/storage/CallContentRow.tsx — Settings › Data › History's "Record tool call content" switch (canvas 1.4.11).
//
// Spec web-ui "Group the Data tab by what kind of data it is" and mcp-gateway
// "Switch call content recording per machine": a sub-row of the tool calls
// retention row, on by default, saved as soon as it is flipped.
import { useId } from "react";
import { useTranslation } from "react-i18next";

import { SettingRow } from "@/components/settings/SettingsLayout";
import { Switch } from "@/components/ui/switch";
import { useCallContentSetting, useSetCallContent } from "@/lib/hooks/useCallContent";

export function CallContentRow() {
  const { t } = useTranslation();
  const id = useId();
  const setting = useCallContentSetting();
  const save = useSetCallContent();
  const enabled = save.isPending ? save.variables : setting.data?.enabled;
  return (
    <SettingRow
      indent
      label={t("settings.data.history.callContent.label")}
      labelFor={id}
      description={t("settings.data.history.callContent.description")}
      status={
        save.isError ? (
          <span className="text-xs text-danger">
            {t("settings.data.history.callContent.notSaved")}
          </span>
        ) : null
      }
    >
      <Switch
        id={id}
        checked={enabled ?? true}
        disabled={setting.isPending || save.isPending}
        onCheckedChange={(on) => save.mutate(on)}
      />
    </SettingRow>
  );
}
