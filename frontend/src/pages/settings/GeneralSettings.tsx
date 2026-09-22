// frontend/src/pages/settings/GeneralSettings.tsx
//
// Settings → General: client-side preferences persisted in localStorage — the
// default rows-per-page every list table seeds from, and the preferred
// external editor Coffer opens managed files with from its read-only viewers.
//
// Both rows use the same shadcn Select. The editor picker lists "system
// default" plus the editors the daemon detected as installed, and a "Custom…"
// entry that reveals a text field for any other app name or launch command.
// An empty value means the OS default. Only the chosen value is stored — it is
// never sent to the daemon except transiently as the target when opening a file.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DaemonResidencySettings } from "./DaemonResidencySettings";
import { Input } from "@/components/ui/input";
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

/** Sentinel option values — never stored; the stored value is the launcher. */
const DEFAULT_OPTION = "__default__";
const CUSTOM_OPTION = "__custom__";

export function GeneralSettings() {
  const { t } = useTranslation();
  const pageSize = useDefaultPageSize();
  const setPageSize = useSetDefaultPageSize();
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
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t("settings.general.title")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex items-center justify-between gap-4">
            <div className="space-y-0.5">
              <p className="text-sm font-medium">{t("settings.general.pageSize")}</p>
              <p className="text-sm text-muted-foreground">{t("settings.general.pageSizeHelp")}</p>
            </div>
            <Select value={String(pageSize)} onValueChange={(v) => setPageSize(Number(v))}>
              <SelectTrigger className="w-44" aria-label={t("settings.general.pageSize")}>
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
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="space-y-0.5">
              <p className="text-sm font-medium">{t("settings.general.preferredEditor")}</p>
              <p className="text-sm text-muted-foreground">
                {t("settings.general.preferredEditorHelp")}
              </p>
            </div>
            <div className="flex w-44 shrink-0 flex-col gap-2">
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
          </div>
        </CardContent>
      </Card>
      {/* What starts Coffer's daemon and what ends it. A page about how the
          app behaves is where a user looks for "why was it not running". */}
      <DaemonResidencySettings />
    </div>
  );
}
