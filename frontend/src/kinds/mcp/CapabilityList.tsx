// frontend/src/kinds/mcp/CapabilityList.tsx
//
// A server's tools / resources / prompts rendered through the shared DataTable
// (unified with the MCP-servers, Agents, and audit surfaces): a search box, a
// status filter (all/enabled/disabled), pagination, and a per-row enable
// switch. Tools additionally expose their input_schema as an expandable row
// detail. The enable/disable mutations keep per-row in-flight state so toggling
// one capability never disables the switches on the others.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { DataTable, type Column, type FilterDef } from "@/components/DataTable";
import type { components } from "@/lib/api/types";
import { useDisableCapability, useEnableCapability } from "@/lib/hooks/useMcpCapabilityMutations";
import { CapabilityBulkActions } from "./CapabilityBulkActions";

type ToolView = components["schemas"]["MCPToolView"];
type ResourceView = components["schemas"]["MCPResourceView"];
type PromptView = components["schemas"]["MCPPromptView"];
type CapabilityKind = "tool" | "resource" | "prompt";

interface Props {
  serverName: string;
  kind: CapabilityKind;
  tools?: ToolView[];
  resources?: ResourceView[];
  prompts?: PromptView[];
  // Set when the /capabilities fetch failed. An errored fetch yields an
  // undefined list — the same shape as a genuinely empty upstream — so we must
  // distinguish them: a failure shows a load-error message, not "nothing
  // discovered" (which would wrongly imply the upstream has no such capability).
  error?: unknown;
}

interface RowDescriptor {
  key: string;
  prefixed: string;
  description: string | null | undefined;
  enabled: boolean;
  schema?: Record<string, unknown>;
}

function ToggleSwitch({
  serverName,
  kind,
  row,
}: {
  serverName: string;
  kind: CapabilityKind;
  row: RowDescriptor;
}) {
  const { t } = useTranslation();
  const enable = useEnableCapability();
  const disable = useDisableCapability();
  // Per-row in-flight state: this switch is the only one toggling, so a single
  // boolean suffices (the per-row scope is naturally enforced by component
  // instance rather than a shared key set).
  const [pending, setPending] = useState(false);

  return (
    <Switch
      checked={row.enabled}
      disabled={pending}
      aria-label={t("mcp.capabilities.toggleAria", { kind, key: row.key })}
      onClick={(e) => e.stopPropagation()}
      onCheckedChange={(checked) => {
        const m = checked ? enable : disable;
        setPending(true);
        m.mutate(
          {
            serverName,
            capabilityType: kind,
            capabilityKey: row.key,
          },
          { onSettled: () => setPending(false) },
        );
      }}
    />
  );
}

export function CapabilityList(props: Props) {
  const { t } = useTranslation();
  const { serverName, kind } = props;
  const rows = toRows(props);

  // Render the same DataTable (search + status filter + per-row enable) for
  // every kind, even when empty, so the Resources/Prompts tabs stay visually
  // consistent with Tools. A truly empty upstream shows the kind-specific
  // "nothing discovered" copy; a non-empty list filtered to zero shows the
  // generic "no matches" message instead.
  const emptyKey =
    kind === "tool"
      ? "mcp.capabilities.emptyTool"
      : kind === "resource"
        ? "mcp.capabilities.emptyResource"
        : "mcp.capabilities.emptyPrompt";
  const emptyMessage = props.error
    ? t("mcp.capabilities.loadError")
    : rows.length === 0
      ? t(emptyKey)
      : t("mcp.capabilities.noMatches");

  const hasSchema = rows.some((r) => r.schema);

  const columns: Column<RowDescriptor>[] = [
    {
      key: "name",
      header: t("mcp.capabilities.header.name"),
      cell: (row) => (
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <code className="text-sm font-semibold">{row.key}</code>
            <Badge variant="outline" className="font-mono text-xs">
              {row.prefixed}
            </Badge>
          </div>
          {row.description ? (
            <p className="mt-1 text-sm text-muted-foreground">{row.description}</p>
          ) : null}
        </div>
      ),
    },
    {
      key: "enabled",
      header: t("mcp.capabilities.header.enabled"),
      className: "w-24 text-right",
      cell: (row) => <ToggleSwitch serverName={serverName} kind={kind} row={row} />,
    },
  ];

  const filters: FilterDef<RowDescriptor>[] = [
    {
      key: "status",
      label: t("mcp.capabilities.statusFilter"),
      allLabel: t("resources.status.all"),
      accessor: (row) => (row.enabled ? "enabled" : "disabled"),
      options: [
        { value: "enabled", label: t("common.enabled") },
        { value: "disabled", label: t("common.disabled") },
      ],
    },
  ];

  return (
    <DataTable
      rows={rows}
      columns={columns}
      rowKey={(row) => row.key}
      search={{
        accessor: (row) => row.key,
        placeholder: t("mcp.capabilities.searchPlaceholder"),
      }}
      filters={filters}
      // Row multi-select with bulk Enable/Disable. The checkbox column coexists
      // with getRowDetail (DataTable renders it before the expand chevron) and
      // with the per-row ToggleSwitch; select-all spans the current
      // search/status-filtered set across pages.
      selection={{
        ariaSelectAll: t("common.bulk.selectAll"),
        ariaSelectRow: (row) => `${t("common.bulk.selectRow")}: ${row.key}`,
        bulkLabel: (count) => t("common.bulk.selected", { count }),
        clearLabel: t("common.clear"),
        renderBulkActions: ({ selectedRows, clear }) => (
          <CapabilityBulkActions
            serverName={serverName}
            kind={kind}
            rows={selectedRows}
            onDone={clear}
          />
        ),
      }}
      // Only tools carry an input_schema; expose it as an expandable detail so
      // a row toggles open to its pretty-printed JSON. Resources/prompts have
      // no schema, so the table stays flat for those kinds.
      getRowDetail={
        hasSchema
          ? (row) =>
              row.schema ? (
                <pre className="overflow-auto px-4 py-3 text-xs">
                  {JSON.stringify(row.schema, null, 2)}
                </pre>
              ) : (
                <div className="px-4 py-3 text-xs text-muted-foreground">
                  {t("mcp.capabilities.noSchema")}
                </div>
              )
          : undefined
      }
      emptyMessage={emptyMessage}
    />
  );
}

function toRows(props: Props): RowDescriptor[] {
  if (props.kind === "tool" && props.tools) {
    return props.tools.map((t) => ({
      key: t.original_name,
      prefixed: t.prefixed_name,
      description: t.description,
      enabled: t.enabled,
      schema: t.input_schema as Record<string, unknown> | undefined,
    }));
  }
  if (props.kind === "resource" && props.resources) {
    return props.resources.map((r) => ({
      key: r.original_uri,
      prefixed: r.prefixed_uri,
      description: r.description,
      enabled: r.enabled,
    }));
  }
  if (props.kind === "prompt" && props.prompts) {
    return props.prompts.map((p) => ({
      key: p.original_name,
      prefixed: p.prefixed_name,
      description: p.description,
      enabled: p.enabled,
    }));
  }
  return [];
}
