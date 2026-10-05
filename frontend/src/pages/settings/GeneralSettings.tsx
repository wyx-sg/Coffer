// frontend/src/pages/settings/GeneralSettings.tsx
//
// Settings → General (canvas 1.4.01): preferences for this browser and this
// Mac, in three sections — Appearance (the interface language and the theme,
// each a segmented choice applied at once), Speech-to-text (the connection and
// model that transcribe voice; spec internal-engine "Show the speech-to-text
// pair in Settings › General", built by its own work item and mounted unchanged
// here), and Tables and files (the default rows per page every list table seeds
// from, and the editor Coffer opens managed files with). Everything saves as it
// changes; there is no Save button. (The experimental features are switched on
// the dev-only Features tab, not here.)
//
// The editor picker lists "system default" plus the editors the daemon
// detected as installed, and a "Custom…" entry that reveals a text field for
// any other app name or launch command. An empty value means the OS default.
// Only the chosen value is stored — it is never sent to the daemon except
// transiently as the target when opening a file.
//
// The Agents and terminal section is built the same way for the preferred
// terminal (spec web-ui "Let the user choose a terminal"): "System terminal",
// the terminals the daemon detected, and "Custom…", a command template that
// must hold `{command}` (and may hold `{cwd}`) or it is not saved. Beside it the
// hand-off agent (spec web-ui "Let the user choose the hand-off agent"): Claude
// Code or Codex, among the managed ones. Check skills for updates (spec
// skill-manager "Hand a Git-imported skill's update to an agent") sits there
// too: how often this Mac fetches the sources of skills added from Git.
import { useTranslation } from "react-i18next";

import { EditorPicker } from "@/components/settings/general/EditorPicker";
import { HandoffAgentPicker } from "@/components/settings/general/HandoffAgentPicker";
import { SkillUpdateCheckPicker } from "@/components/settings/general/SkillUpdateCheckPicker";
import { TerminalPicker } from "@/components/settings/general/TerminalPicker";
import {
  SETTINGS_STACK,
  SettingRow,
  SettingsSection,
  SettingsTabHeader,
} from "@/components/settings/SettingsLayout";
import { Segmented } from "@/components/ui/segmented";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PAGE_SIZE_OPTIONS, useDefaultPageSize, useSetDefaultPageSize } from "@/lib/preferences";
import { useSetThemePreference, useThemePreference, type ThemePreference } from "@/lib/theme";
import { EngineSettings } from "./EngineSettings";

/** Design order: the two fixed looks, then following the OS. */
const THEME_ORDER: readonly ThemePreference[] = ["light", "dark", "system"];
const THEME_LABEL_KEYS: Record<ThemePreference, string> = {
  system: "settings.general.themeSystem",
  light: "settings.general.themeLight",
  dark: "settings.general.themeDark",
};

type Language = "en" | "zh";

export function GeneralSettings() {
  const { t, i18n } = useTranslation();
  const pageSize = useDefaultPageSize();
  const setPageSize = useSetDefaultPageSize();
  const theme = useThemePreference();
  const setTheme = useSetThemePreference();
  const language: Language = i18n.language?.startsWith("zh") ? "zh" : "en";

  return (
    <div className="flex flex-col gap-5">
      <SettingsTabHeader title={t("settings.tabs.general")} intro={t("settings.general.intro")} />
      <div className={SETTINGS_STACK}>
        <SettingsSection title={t("settings.general.appearance")}>
          <SettingRow
            label={t("settings.general.language")}
            description={t("settings.general.languageHelp")}
          >
            <Segmented<Language>
              label={t("settings.general.language")}
              value={language}
              onChange={(code) => void i18n.changeLanguage(code)}
              options={[
                { value: "en", label: "English" },
                { value: "zh", label: "中文" },
              ]}
            />
          </SettingRow>
          <SettingRow
            label={t("settings.general.theme")}
            description={t("settings.general.themeHelp")}
          >
            <Segmented<ThemePreference>
              label={t("settings.general.theme")}
              value={theme}
              onChange={setTheme}
              options={THEME_ORDER.map((p) => ({ value: p, label: t(THEME_LABEL_KEYS[p]) }))}
            />
          </SettingRow>
        </SettingsSection>

        <EngineSettings />

        <SettingsSection title={t("settings.general.tablesAndFiles")}>
          <SettingRow
            label={t("settings.general.pageSize")}
            description={t("settings.general.pageSizeHelp")}
          >
            <Select value={String(pageSize)} onValueChange={(v) => setPageSize(Number(v))}>
              <SelectTrigger className="w-24" aria-label={t("settings.general.pageSize")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PAGE_SIZE_OPTIONS.map((n) => (
                  <SelectItem key={n} value={String(n)}>
                    {n}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </SettingRow>
          <SettingRow
            label={t("settings.general.preferredEditor")}
            description={t("settings.general.preferredEditorHelp")}
          >
            <EditorPicker />
          </SettingRow>
        </SettingsSection>

        <SettingsSection title={t("settings.general.agentsAndTerminal")}>
          <SettingRow
            label={t("settings.general.preferredTerminal")}
            description={t("settings.general.preferredTerminalHelp")}
          >
            <TerminalPicker />
          </SettingRow>
          <SettingRow
            label={t("settings.general.handoffAgent")}
            description={t("settings.general.handoffAgentHelp")}
          >
            <HandoffAgentPicker />
          </SettingRow>
          <SettingRow
            label={t("settings.general.skillUpdateCheck")}
            description={t("settings.general.skillUpdateCheckHelp")}
          >
            <SkillUpdateCheckPicker />
          </SettingRow>
        </SettingsSection>
      </div>
    </div>
  );
}
