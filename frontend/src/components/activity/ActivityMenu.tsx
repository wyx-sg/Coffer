// src/components/activity/ActivityMenu.tsx — the page's ⋯ menu: "Export filtered records…" as JSON or CSV.
//
// The page header carries no export button of its own (spec web-ui "Export
// the filtered Activity records from the overflow menu"): the export lives
// here, and writes every record of the visible tab that matches its filters.
import { useState } from "react";
import { FileJson, FileSpreadsheet, MoreHorizontal } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useToast } from "@/components/ui/toast";
import type { SourceParams } from "@/lib/api/activity";
import { translateApiError } from "@/lib/api/errors";
import { collectForExport, saveFile, toCsv, toJson } from "@/lib/activity/export";
import type { ActivityRecord, ActivityTab } from "@/lib/activity/records";

interface Props {
  tab: ActivityTab;
  specs: SourceParams[];
  keep: (r: ActivityRecord) => boolean;
}

function stamp(now: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}${p(now.getMonth() + 1)}${p(now.getDate())}-${p(now.getHours())}${p(now.getMinutes())}`;
}

export function ActivityMenu({ tab, specs, keep }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const run = async (format: "json" | "csv") => {
    setBusy(true);
    try {
      const records = await collectForExport(specs, keep);
      const name = `coffer-activity-${tab}-${stamp(new Date())}.${format}`;
      if (format === "json") saveFile(name, "application/json", toJson(records));
      else saveFile(name, "text/csv", toCsv(records));
      toast.success(t("activity.menu.done", { count: records.length }));
      setOpen(false);
    } catch (error) {
      toast.error(translateApiError(t, error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={t("activity.menu.label")}>
          <MoreHorizontal />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-60 p-1">
        <div role="menu" aria-label={t("activity.menu.heading")} className="flex flex-col">
          <div className="px-2 pb-1 pt-1.5 text-2xs font-semibold text-text-subtle">
            {t("activity.menu.heading")}
          </div>
          <button
            type="button"
            role="menuitem"
            disabled={busy}
            onClick={() => void run("json")}
            className="flex h-8 items-center gap-2 rounded-sm px-2 text-left text-sm text-text hover:bg-surface-hover disabled:opacity-disabled"
          >
            <FileJson className="size-3.5 text-text-muted" aria-hidden />
            {t("activity.menu.json")}
          </button>
          <button
            type="button"
            role="menuitem"
            disabled={busy}
            onClick={() => void run("csv")}
            className="flex h-8 items-center gap-2 rounded-sm px-2 text-left text-sm text-text hover:bg-surface-hover disabled:opacity-disabled"
          >
            <FileSpreadsheet className="size-3.5 text-text-muted" aria-hidden />
            {t("activity.menu.csv")}
          </button>
          <p className="px-2 pb-1.5 pt-1 text-2xs text-text-subtle">{t("activity.menu.note")}</p>
        </div>
      </PopoverContent>
    </Popover>
  );
}
