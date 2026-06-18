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
import {
  getPreferredEditor,
  PAGE_SIZE_OPTIONS,
  useDefaultPageSize,
  useSetDefaultPageSize,
  useSetPreferredEditor,
} from "@/lib/preferences";
import { isTauri } from "@/lib/tauri";

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
 */
export function GeneralSettings() {
  const { t } = useTranslation();
  const pageSize = useDefaultPageSize();
  const setPageSize = useSetDefaultPageSize();
  const setPreferredEditor = useSetPreferredEditor();
  const [editor, setEditor] = useState(getPreferredEditor);

  const commitEditor = (value: string) => {
    setEditor(value);
    setPreferredEditor(value);
  };

  const browse = async () => {
    const picked = await pickEditorApp();
    if (picked) commitEditor(picked);
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
          <div className="flex items-center gap-2">
            <Input
              value={editor}
              placeholder={t("settings.general.preferredEditorPlaceholder")}
              onChange={(e) => setEditor(e.target.value)}
              onBlur={(e) => commitEditor(e.target.value)}
              className="w-56"
              aria-label={t("settings.general.preferredEditor")}
            />
            {isTauri() ? (
              <Button type="button" variant="outline" size="sm" onClick={() => void browse()}>
                {t("settings.general.preferredEditorBrowse")}
              </Button>
            ) : null}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
