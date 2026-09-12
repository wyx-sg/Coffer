import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, ChevronsUpDown } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
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
import { cn } from "@/lib/utils";
import { DaemonPortCard } from "./DaemonPortCard";

/**
 * General display preferences (client-side, persisted in localStorage): the
 * default rows-per-page every list table seeds from, and the preferred external
 * editor Coffer opens managed files with from its read-only file viewers.
 *
 * The editor control is an edit-in-place combobox: the text field is always
 * editable (type any app name / launch command directly), and the chevron opens
 * a picker of editors the daemon detected as installed — plus "system default".
 * An empty value means the OS default.
 * Only the chosen value is stored — never sent to the daemon except transiently
 * as the target when opening a file.
 *
 * Below them sits the one daemon-side setting that belongs on this tab: the
 * address this page is served at, and the port behind it (DaemonPortCard).
 */
export function GeneralSettings() {
  const { t } = useTranslation();
  const pageSize = useDefaultPageSize();
  const setPageSize = useSetDefaultPageSize();
  const setPreferredEditor = useSetPreferredEditor();
  const { data: detected = [] } = useDetectedEditors();
  const [editor, setEditor] = useState(getPreferredEditor);
  const [pickerOpen, setPickerOpen] = useState(false);

  const commitEditor = (value: string) => {
    setEditor(value);
    setPreferredEditor(value);
  };

  const pick = (value: string) => {
    commitEditor(value);
    setPickerOpen(false);
  };

  // System default + detected editors. A custom editor is typed straight into
  // the field, so there's no separate "custom" entry or expanded text box.
  const options = [
    { label: t("settings.general.preferredEditorSystemDefault"), value: "" },
    ...detected,
  ];

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

          <div className="flex items-center justify-between gap-4">
            <div className="space-y-0.5">
              <p className="text-sm font-medium">{t("settings.general.preferredEditor")}</p>
              <p className="text-sm text-muted-foreground">
                {t("settings.general.preferredEditorHelp")}
              </p>
            </div>
            <div className="relative w-44 shrink-0">
              <Input
                value={editor}
                placeholder={t("settings.general.preferredEditorSystemDefault")}
                onChange={(e) => setEditor(e.target.value)}
                onBlur={(e) => commitEditor(e.target.value)}
                className="pr-9"
                aria-label={t("settings.general.preferredEditor")}
              />
              <Popover open={pickerOpen} onOpenChange={setPickerOpen}>
                <PopoverTrigger asChild>
                  <button
                    type="button"
                    className="absolute inset-y-0 right-0 flex w-9 items-center justify-center rounded-r-md text-muted-foreground hover:text-foreground"
                    aria-label={t("settings.general.preferredEditorChoose")}
                  >
                    <ChevronsUpDown className="size-4" />
                  </button>
                </PopoverTrigger>
                <PopoverContent align="end" className="w-44 p-1">
                  {options.map((opt) => (
                    <button
                      key={opt.value || "__default__"}
                      type="button"
                      onClick={() => pick(opt.value)}
                      className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent"
                    >
                      <Check
                        className={cn(
                          "size-4 shrink-0",
                          editor === opt.value ? "opacity-100" : "opacity-0",
                        )}
                      />
                      <span className="truncate">{opt.label}</span>
                    </button>
                  ))}
                </PopoverContent>
              </Popover>
            </div>
          </div>
        </CardContent>
      </Card>

      <DaemonPortCard />
    </div>
  );
}
