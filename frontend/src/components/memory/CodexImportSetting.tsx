// frontend/src/components/memory/CodexImportSetting.tsx
//
// "Codex imports Claude Code's memories itself" (spec memory "Defer to Codex's
// own import from Claude Code"). Where Codex keeps that setting is not
// documented, so the person answers it here; on, Coffer writes no Claude Code
// memory into Codex on this machine — Codex imports them itself — while Codex's
// memories still reach Claude Code. Saved as it changes.
import { useTranslation } from "react-i18next";

import { SettingRow } from "@/components/settings/SettingsLayout";
import { Switch } from "@/components/ui/switch";
import { useSetCodexImport } from "@/lib/hooks/useMemory";

const ID = "memory-codex-import";

interface Props {
  /** The person's answer; `null` while they have not given one. */
  value: boolean | null;
}

export function CodexImportSetting({ value }: Props) {
  const { t } = useTranslation();
  const set = useSetCodexImport();
  return (
    <SettingRow
      label={t("memory.codexImport.label")}
      labelFor={ID}
      description={t("memory.codexImport.description")}
      status={
        value ? (
          <span className="text-xs text-text-muted">{t("memory.codexImport.on")}</span>
        ) : undefined
      }
    >
      <Switch
        id={ID}
        checked={value === true}
        disabled={set.isPending}
        onCheckedChange={(on) => set.mutate(on)}
      />
    </SettingRow>
  );
}
