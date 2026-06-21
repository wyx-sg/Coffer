import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { isTauri } from "@/lib/tauri";

// Sentinel Select values (Radix Select items can't be the empty string).
const DEFAULT_OPT = "__default__"; // OS default — stored preference is ""
const CUSTOM_OPT = "__custom__"; // free-form app name / launch command / .app path

/** Pick an application bundle on the desktop (macOS apps are .app directories). */
async function pickEditorApp(): Promise<string | null> {
  const { open } = await import("@tauri-apps/plugin-dialog");
  const picked = await open({ directory: true, defaultPath: "/Applications" });
  return typeof picked === "string" ? picked : null;
}

/**
 * General display preferences (client-side, persisted in localStorage): the
 * default rows-per-page every list table seeds from, and the preferred external
 * editor Coffer opens managed files with from its read-only file viewers.
 *
 * The editor is chosen from a picker of editors the daemon detected as installed
 * (a browser can't enumerate apps), with a "system default" option and a custom
 * escape hatch for anything unlisted. Only the chosen value is stored — never
 * sent to the daemon except transiently as the target when opening a file.
 */
export function GeneralSettings() {
  const { t } = useTranslation();
  const pageSize = useDefaultPageSize();
  const setPageSize = useSetDefaultPageSize();
  const setPreferredEditor = useSetPreferredEditor();
  const { data: detected = [] } = useDetectedEditors();
  const [editor, setEditor] = useState(getPreferredEditor);
  const [customMode, setCustomMode] = useState(false);

  const isKnown = detected.some((e) => e.value === editor);
  // A non-empty value that isn't a detected editor is a custom entry (typed, or
  // picked via Browse); custom mode is also entered explicitly from the picker.
  const showCustom = customMode || (editor !== "" && !isKnown);
  const selectValue = showCustom ? CUSTOM_OPT : editor === "" ? DEFAULT_OPT : editor;

  const commitEditor = (value: string) => {
    setEditor(value);
    setPreferredEditor(value);
  };

  const onSelect = (v: string) => {
    if (v === DEFAULT_OPT) {
      setCustomMode(false);
      commitEditor("");
    } else if (v === CUSTOM_OPT) {
      setCustomMode(true); // reveal the input; keep current text as the starting point
    } else {
      setCustomMode(false);
      commitEditor(v);
    }
  };

  const browse = async () => {
    const picked = await pickEditorApp();
    if (picked) {
      setCustomMode(true);
      commitEditor(picked);
    }
  };

  return (
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
        </div>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
          <div className="space-y-0.5">
            <p className="text-sm font-medium">{t("settings.general.preferredEditor")}</p>
            <p className="text-sm text-muted-foreground">
              {t("settings.general.preferredEditorHelp")}
            </p>
          </div>
          <div className="flex flex-col items-stretch gap-2 sm:items-end">
            <Select value={selectValue} onValueChange={onSelect}>
              <SelectTrigger className="w-56" aria-label={t("settings.general.preferredEditor")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={DEFAULT_OPT}>
                  {t("settings.general.preferredEditorSystemDefault")}
                </SelectItem>
                {detected.map((e) => (
                  <SelectItem key={e.value} value={e.value}>
                    {e.label}
                  </SelectItem>
                ))}
                <SelectItem value={CUSTOM_OPT}>
                  {t("settings.general.preferredEditorCustom")}
                </SelectItem>
              </SelectContent>
            </Select>
            {showCustom && (
              <div className="flex items-center gap-2">
                <Input
                  value={editor}
                  placeholder={t("settings.general.preferredEditorPlaceholder")}
                  onChange={(e) => setEditor(e.target.value)}
                  onBlur={(e) => commitEditor(e.target.value)}
                  className="w-56"
                  aria-label={t("settings.general.preferredEditorCustom")}
                />
                {isTauri() ? (
                  <Button type="button" variant="outline" size="sm" onClick={() => void browse()}>
                    {t("settings.general.preferredEditorBrowse")}
                  </Button>
                ) : null}
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
