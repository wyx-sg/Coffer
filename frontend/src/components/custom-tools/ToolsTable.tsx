// src/components/custom-tools/ToolsTable.tsx — a group's tools (4.2.01): each one's switch, request, changes-data
// flag, reach (inherited control: Same as the group by default) and last 24 hours; "N of M on · All on · All off"
// on the title row; the pencil (or the row) opens the drawer.
import { useTranslation } from "react-i18next";
import { Pencil, Plus } from "lucide-react";

import { Section } from "@/components/Section";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { agentPrefix, toolsOn } from "@/lib/customTools/groups";
import { useSetAllCustomTools, useToggleCustomTool } from "@/lib/hooks/useCustomTools";
import { cn } from "@/lib/utils";
import { ToolReachCell } from "./ToolReachCell";

interface Props {
  group: CustomToolGroup;
  onOpenTool: (tool: string) => void;
  onAddRequest: () => void;
}

const GRID = "grid grid-cols-[40px_minmax(0,1fr)_168px_72px_56px_32px] items-center gap-3 px-2";

/** A 24-hour count; a tool with no call in 24 hours reads "—" in both columns. */
function Count({
  value,
  none,
  danger = false,
}: {
  value: number;
  none: boolean;
  danger?: boolean;
}) {
  return (
    <span className={cn("text-xs tabular-nums", danger && value > 0 ? "text-danger" : "text-text")}>
      {none ? "—" : value}
    </span>
  );
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

  return (
    <Section
      title={t("customTools.tools.heading")}
      as="h2"
      gap="tight"
      labelled
      actions={
        <div className="flex items-center gap-2 text-xs">
          <span className="text-text-muted">
            {t("customTools.tools.countOn", { on, total: group.tools.length })}
          </span>
          <span className="text-text-subtle">·</span>
          <button
            type="button"
            className="font-label text-accent-text hover:underline disabled:opacity-disabled disabled:no-underline"
            disabled={setAll.isPending || on === group.tools.length}
            onClick={() => switchAll(true)}
          >
            {t("customTools.tools.allOn")}
          </button>
          <span className="text-text-subtle">·</span>
          <button
            type="button"
            className="font-label text-accent-text hover:underline disabled:opacity-disabled disabled:no-underline"
            disabled={setAll.isPending || on === 0}
            onClick={() => switchAll(false)}
          >
            {t("customTools.tools.allOff")}
          </button>
        </div>
      }
    >
      <p className="text-xs text-text-muted">
        {t("customTools.tools.description", { prefix: agentPrefix(group.name) })}
      </p>
      <div role="table" aria-label={t("customTools.tools.heading")}>
        <div
          role="row"
          className={cn(
            GRID,
            "h-8 border-b border-border-subtle text-2xs font-semibold text-text-muted",
          )}
        >
          <span role="columnheader">
            <span className="sr-only">{t("customTools.tools.switch")}</span>
          </span>
          <span role="columnheader">{t("customTools.tools.colTool")}</span>
          <span role="columnheader">{t("customTools.fields.availableTo")}</span>
          <span role="columnheader" className="text-right">
            {t("customTools.tools.colCalls")}
          </span>
          <span role="columnheader" className="text-right">
            {t("customTools.tools.colErrors")}
          </span>
          <span />
        </div>
        {group.tools.length === 0 ? (
          <p className="py-4 text-center text-xs text-text-muted">{t("customTools.tools.empty")}</p>
        ) : null}
        {group.tools.map((tool) => (
          <div
            key={tool.name}
            role="row"
            className={cn(
              GRID,
              "min-h-[49px] cursor-pointer border-b border-border-subtle py-1.5 hover:bg-surface-hover",
            )}
            onClick={() => onOpenTool(tool.name)}
          >
            {/* The switch acts on its own; it never also opens the row. */}
            <span role="cell" onClick={(e) => e.stopPropagation()} className="inline-flex">
              <Switch
                checked={tool.enabled}
                disabled={toggle.isPending || setAll.isPending}
                aria-label={t("customTools.tools.switchTool", { name: tool.name })}
                onCheckedChange={(enabled) => toggle.mutate({ tool: tool.name, enabled })}
              />
            </span>
            <span role="cell" className="min-w-0">
              <span
                className={cn(
                  "block truncate font-mono text-sm",
                  tool.enabled ? "text-text" : "text-text-muted",
                )}
              >
                {tool.name}
              </span>
              <span className="flex min-w-0 items-center gap-1.5">
                <span className="truncate text-xs text-text-muted">
                  {tool.method} {tool.path}
                </span>
                {tool.changes_data ? (
                  <Badge variant="warning">{t("customTools.tools.changesData")}</Badge>
                ) : null}
              </span>
            </span>
            {/* The control opens its own popover; it never also opens the row. */}
            <span role="cell" onClick={(e) => e.stopPropagation()} className="inline-flex">
              <ToolReachCell group={group} tool={tool} />
            </span>
            <span role="cell" className="text-right">
              <Count value={tool.calls_24h} none={tool.calls_24h === 0} />
            </span>
            <span role="cell" className="text-right">
              <Count value={tool.failures_24h} none={tool.calls_24h === 0} danger />
            </span>
            <span role="cell">
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={t("customTools.tools.edit", { name: tool.name })}
                onClick={(e) => {
                  e.stopPropagation();
                  onOpenTool(tool.name);
                }}
              >
                <Pencil aria-hidden />
              </Button>
            </span>
          </div>
        ))}
      </div>
      <div className="flex justify-end pt-2">
        <Button variant="outline" size="sm" onClick={onAddRequest}>
          <Plus aria-hidden />
          {t("customTools.tools.addRequest")}
        </Button>
      </div>
    </Section>
  );
}
