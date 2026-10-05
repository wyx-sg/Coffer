// frontend/src/components/settings/general/SkillUpdateCheckPicker.tsx
//
// Settings › General: how often this machine checks Git-imported skills for
// updates in the background (spec skill-manager "Hand a Git-imported skill's
// update to an agent"). The choice is the daemon's, kept in
// ~/.coffer/daemon-config.json and in effect at once; "Only when I ask" stops
// the background fetch, and Check for updates on a skill works whatever it says.
import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { SkillUpdateCheckInterval } from "@/lib/api/skills";
import { useSetSkillUpdateCheck, useSkillUpdateCheck } from "@/lib/hooks/useSkills";

const OPTIONS: readonly { value: SkillUpdateCheckInterval; key: string }[] = [
  { value: "6h", key: "skillUpdateCheck6h" },
  { value: "1d", key: "skillUpdateCheck1d" },
  { value: "7d", key: "skillUpdateCheck7d" },
  { value: "manual", key: "skillUpdateCheckManual" },
];

export function SkillUpdateCheckPicker() {
  const { t } = useTranslation();
  const setting = useSkillUpdateCheck();
  const set = useSetSkillUpdateCheck();
  return (
    <Select
      value={setting.data?.interval ?? "6h"}
      disabled={!setting.data || set.isPending}
      onValueChange={(next) => set.mutate(next as SkillUpdateCheckInterval)}
    >
      <SelectTrigger className="w-56" aria-label={t("settings.general.skillUpdateCheck")}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {OPTIONS.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {t(`settings.general.${o.key}`)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
