// src/components/custom-tools/ToolsTable.tsx — a group's tools: each one's switch, request, changes-data
// flag, reach override and last 24 hours; All on / All off; a row opens the tool's drawer.
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";

import { DataTable, type Column } from "@/components/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import type { CustomTool, CustomToolGroup } from "@/lib/api/customTools";
import { toolsOn } from "@/lib/customTools/groups";
import { useSetAllCustomTools, useToggleCustomTool } from "@/lib/hooks/useCustomTools";

interface Props {
  group: CustomToolGroup;
  onOpenTool: (tool: string) => void;
  onAddRequest: () => void;
}

export function ToolsTable({ group, onOpenTool, onAddRequest }: Props) {
  const { t } = useTranslation();
  const toggle = useToggleCustomTool(group.name);
  const setAll = useSetAllCustomTools(group.name);
  const on = toolsOn(group.tools);
  const switchAll = (enabled: boolean) =>
    setAll.mutate({
      enabled,
      tools: group.tools.filter((tool) => tool.enabled !== enabled).map((tool) => tool.name),
    });

  const columns: Column<CustomTool>[] = [
    {
      key: "enabled",
      header: <span className="sr-only">{t("customTools.tools.switch")}</span>,
      className: "w-12",
      cell: (tool) => (
        // The switch acts on its own; it never also opens the row.
        <span onClick={(e) => e.stopPropagation()} className="inline-flex">
          <Switch
            checked={tool.enabled}
            disabled={toggle.isPending || setAll.isPending}
            aria-label={t("customTools.tools.switchTool", { name: tool.name })}
            onCheckedChange={(enabled) => toggle.mutate({ tool: tool.name, enabled })}
          />
        </span>
      ),
    },
    {
      key: "tool",
      header: t("customTools.tools.colTool"),
      cell: (tool) => (
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="truncate font-mono text-sm font-label">{tool.name}</span>
            {tool.changes_data ? (
              <Badge variant="secondary">{t("customTools.tools.changesData")}</Badge>
            ) : null}
          </div>
          <div className="truncate font-mono text-xs text-text-muted">
            {tool.method} {tool.path}
          </div>
        </div>
      ),
    },
    {
      key: "reach",
      header: t("customTools.fields.availableTo"),
      cell: (tool) =>
        tool.reach_override === null ? (
          <span className="text-xs text-text-muted">{t("customTools.tools.groupDefault")}</span>
        ) : (
          <Badge variant="outline">{t("customTools.tools.override")}</Badge>
        ),
    },
    {
      key: "calls",
      header: t("customTools.tools.colCalls"),
      className: "text-right",
      cell: (tool) => <span className="text-xs">{tool.calls_24h}</span>,
    },
    {
      key: "errors",
      header: t("customTools.tools.colErrors"),
      className: "text-right",
      cell: (tool) => (
        <span className={tool.failures_24h > 0 ? "text-xs text-danger" : "text-xs"}>
          {tool.failures_24h}
        </span>
      ),
    },
  ];

  return (
    <section aria-labelledby="ct-tools" className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <h2 id="ct-tools" className="text-sm font-semibold">
          {t("customTools.tools.title", { on, total: group.tools.length })}
        </h2>
        <div className="flex items-center gap-1 text-xs">
          <Button
            size="sm"
            variant="ghost"
            disabled={setAll.isPending || on === group.tools.length}
            onClick={() => switchAll(true)}
          >
            {t("customTools.tools.allOn")}
          </Button>
          <span className="text-text-subtle">·</span>
          <Button
            size="sm"
            variant="ghost"
            disabled={setAll.isPending || on === 0}
            onClick={() => switchAll(false)}
          >
            {t("customTools.tools.allOff")}
          </Button>
        </div>
      </div>
      <DataTable
        rows={group.tools}
        columns={columns}
        rowKey={(tool) => tool.name}
        onRowClick={(tool) => onOpenTool(tool.name)}
        pageSize={100}
        emptyMessage={t("customTools.tools.empty")}
      />
      <Button variant="outline" onClick={onAddRequest}>
        <Plus aria-hidden />
        {t("customTools.tools.addRequest")}
      </Button>
    </section>
  );
}
