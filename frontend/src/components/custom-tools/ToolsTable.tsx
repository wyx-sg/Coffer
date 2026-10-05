// src/components/custom-tools/ToolsTable.tsx — a group's tools (4.2.01): each one's switch, request, changes-data
// flag, exposure (the MCP server Tools tab's control: Auto · Listed, Always listed, Search only; spec mcp-gateway
// "Choose how each tool is exposed") and last 24 hours; "N of M on · All on · All off" on the title row, then a
// toolbar of a name filter and Add request above the table; the pencil (or the row) opens the drawer. A tool has
// no reach of its own: its group's reach decides who sees it.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pencil, Plus } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { HelpTip } from "@/components/HelpTip";
import { SearchInput } from "@/components/SearchInput";
import { Section } from "@/components/Section";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { McpToolExposure } from "@/components/mcp/server/McpToolExposure";
import type { ToolRow } from "@/components/mcp/server/toolRows";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { agentPrefix, toolsOn } from "@/lib/customTools/groups";
import { useSetAllCustomTools, useToggleCustomTool } from "@/lib/hooks/useCustomTools";
import { cn } from "@/lib/utils";

interface Props {
  group: CustomToolGroup;
  /** The group's tools as tool rows, each with its exposure once tiering was read. */
  rows: readonly ToolRow[];
  /** Show the Exposure column (tiering is on and its split was read). */
  showExposure: boolean;
  onOpenTool: (tool: string) => void;
  onAddRequest: () => void;
}

const GRID = "grid items-center gap-3 px-2";
const COLS = "grid-cols-[40px_minmax(0,1fr)_72px_56px_32px]";
const COLS_EXPOSURE = "grid-cols-[40px_minmax(0,1fr)_176px_72px_56px_32px]";

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

/** A tool's exposure control; a tool that is off, or one tiering has not reported, reads "—". */
function ExposureCell({
  serverUid,
  tool,
  exposure,
}: {
  serverUid: string;
  tool: string;
  exposure: ToolRow["exposure"] | undefined;
}) {
  if (!exposure) return <span className="text-xs text-text-subtle">—</span>;
  return <McpToolExposure serverUid={serverUid} tool={tool} exposure={exposure} />;
}

export function ToolsTable({ group, rows, showExposure, onOpenTool, onAddRequest }: Props) {
  const { t } = useTranslation();
  const grid = cn(GRID, showExposure ? COLS_EXPOSURE : COLS);
  const exposureOf = new Map(rows.map((r) => [r.key, r.exposure]));
  const toggle = useToggleCustomTool(group.name);
  const setAll = useSetAllCustomTools(group.name);
  const [filter, setFilter] = useState("");
  const q = filter.trim().toLowerCase();
  const shown = group.tools.filter((tool) => !q || tool.name.toLowerCase().includes(q));
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
      <div className="flex items-center gap-2">
        <SearchInput
          value={filter}
          onChange={setFilter}
          placeholder={t("customTools.tools.filter")}
          ariaLabel={t("customTools.tools.filter")}
          className="max-w-xs flex-1"
        />
        <Button variant="outline" size="sm" className="ml-auto" onClick={onAddRequest}>
          <Plus aria-hidden />
          {t("customTools.tools.addRequest")}
        </Button>
      </div>
      <div role="table" aria-label={t("customTools.tools.heading")}>
        <div
          role="row"
          className={cn(
            grid,
            "h-8 border-b border-border-subtle text-2xs font-semibold text-text-muted",
          )}
        >
          <span role="columnheader">
            <span className="sr-only">{t("customTools.tools.switch")}</span>
          </span>
          <span role="columnheader">{t("customTools.tools.colTool")}</span>
          {showExposure ? (
            <span role="columnheader" className="flex items-center gap-1">
              {t("mcp.exposure.col")}
              <HelpTip label={t("mcp.exposure.col")}>{t("mcp.exposure.help")}</HelpTip>
            </span>
          ) : null}
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
        ) : shown.length === 0 ? (
          <EmptyState
            size="compact"
            title={t("customTools.tools.noMatch", { query: filter.trim() })}
            action={
              <Button size="sm" variant="outline" onClick={() => setFilter("")}>
                {t("listStates.clearFilter")}
              </Button>
            }
          />
        ) : null}
        {shown.map((tool) => (
          <div
            key={tool.name}
            role="row"
            className={cn(
              grid,
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
            {showExposure ? (
              // A portal's events bubble through the React tree: keep the row from opening.
              <span role="cell" onClick={(e) => e.stopPropagation()}>
                <ExposureCell
                  serverUid={group.uid}
                  tool={tool.name}
                  exposure={tool.enabled ? exposureOf.get(tool.name) : null}
                />
              </span>
            ) : null}
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
    </Section>
  );
}
