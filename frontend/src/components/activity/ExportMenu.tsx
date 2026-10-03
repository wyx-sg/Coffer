// src/components/activity/ExportMenu.tsx — the header's ghost "Export ⌄": the filtered records as JSON or CSV.
//
// The export lives in the page header (spec web-ui "Export the filtered
// Activity records from the header"), and writes every record of the visible tab that matches
// its filters — not just what is loaded.
import { useState } from "react";
import { ChevronDown, Download, FileJson, FileSpreadsheet } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { ActionMenu } from "@/components/ui/menu";
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

export function ExportMenu({ tab, specs, keep }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [busy, setBusy] = useState(false);

  const run = async (format: "json" | "csv") => {
    setBusy(true);
    try {
      const records = await collectForExport(specs, keep);
      const name = `coffer-activity-${tab}-${stamp(new Date())}.${format}`;
      if (format === "json") saveFile(name, "application/json", toJson(records));
      else saveFile(name, "text/csv", toCsv(records));
      toast.success(t("activity.export.done", { count: records.length }));
    } catch (error) {
      toast.error(translateApiError(t, error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <ActionMenu
      label={t("activity.export.label")}
      trigger={
        <Button variant="ghost" loading={busy} aria-haspopup="menu">
          <Download />
          {t("activity.export.label")}
          <ChevronDown className="text-text-subtle" />
        </Button>
      }
      actions={[
        {
          key: "json",
          label: t("activity.export.json"),
          icon: FileJson,
          onSelect: () => void run("json"),
        },
        {
          key: "csv",
          label: t("activity.export.csv"),
          icon: FileSpreadsheet,
          onSelect: () => void run("csv"),
        },
      ]}
    />
  );
}
