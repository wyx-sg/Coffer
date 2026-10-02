// frontend/src/pages/settings/GeneralSettings.tsx
//
// Settings → General (design 6.2.01): preferences for this browser and this
// Mac, in three sections — Appearance (the interface language and the theme,
// each a segmented choice applied at once), Coffer's model (the model Coffer's
// own engine runs on and speech to text; spec web-ui "Choose Coffer's model in
// Settings › General", built by its own work item and mounted unchanged here),
// and Tables and files (the default rows per page every list table seeds from,
// and the editor Coffer opens managed files with). Everything saves as it
// changes; there is no Save button. (The experimental features are switched on
// the dev-only Features tab, not here.)
//
// The editor picker lists "system default" plus the editors the daemon
// detected as installed, and a "Custom…" entry that reveals a text field for
// any other app name or launch command. An empty value means the OS default.
// Only the chosen value is stored — it is never sent to the daemon except
// transiently as the target when opening a file.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { SettingRow, SettingsSection } from "@/components/settings/SettingsLayout";
import { Input } from "@/components/ui/input";
import { Segmented } from "@/components/ui/segmented";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useDetectedEditors } from "@/lib/hooks/useEditors";
import {
  getPreferredEditor,
  PAGE_SIZE_OPTIONS,
  useDefaultPageSize,
  useSetDefaultPageSize,
  useSetPreferredEditor,
} from "@/lib/preferences";
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

/** Sentinel option values — never stored; the stored value is the launcher. */
const DEFAULT_OPTION = "__default__";
const CUSTOM_OPTION = "__custom__";

function EditorPicker() {
  const { t } = useTranslation();
  const setPreferredEditor = useSetPreferredEditor();
  const { data: detected = [] } = useDetectedEditors();
  const [editor, setEditor] = useState(getPreferredEditor);
  // True once the user picks "Custom…" — keeps the text field open while it
  // is still empty. A stored value no detected editor matches is custom too.
  const [customChosen, setCustomChosen] = useState(false);

  const isDetected = detected.some((d) => d.value === editor);
  const isCustom = customChosen || (editor !== "" && !isDetected);
  const selected = isCustom ? CUSTOM_OPTION : editor === "" ? DEFAULT_OPTION : editor;

  const commitEditor = (value: string) => {
    setEditor(value);
    setPreferredEditor(value);
  };

  const pick = (value: string) => {
    if (value === CUSTOM_OPTION) {
      setCustomChosen(true);
      return;
    }
    setCustomChosen(false);
    commitEditor(value === DEFAULT_OPTION ? "" : value);
  };

  return (
    <div className="flex w-56 flex-col gap-2">
      <Select value={selected} onValueChange={pick}>
        <SelectTrigger aria-label={t("settings.general.preferredEditor")}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={DEFAULT_OPTION}>
            {t("settings.general.preferredEditorSystemDefault")}
          </SelectItem>
          {detected.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
          <SelectItem value={CUSTOM_OPTION}>
            {t("settings.general.preferredEditorCustom")}
          </SelectItem>
        </SelectContent>
      </Select>
      {isCustom ? (
        <Input
          value={editor}
          placeholder={t("settings.general.preferredEditorCustomPlaceholder")}
          onChange={(e) => setEditor(e.target.value)}
          onBlur={(e) => commitEditor(e.target.value.trim())}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
          }}
          aria-label={t("settings.general.preferredEditorCustomCommand")}
        />
      ) : null}
    </div>
  );
}

export function GeneralSettings() {
  const { t, i18n } = useTranslation();
  const pageSize = useDefaultPageSize();
  const setPageSize = useSetDefaultPageSize();
  const theme = useThemePreference();
  const setTheme = useSetThemePreference();
  const language: Language = i18n.language?.startsWith("zh") ? "zh" : "en";

  return (
    <div className="flex flex-col gap-5">
      <p className="text-sm text-text-muted">{t("settings.general.intro")}</p>
      <div className="flex flex-col gap-7">
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
      </div>
    </div>
  );
}
