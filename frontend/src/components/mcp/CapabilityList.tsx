// frontend/src/components/mcp/CapabilityList.tsx
//
// A server's tools / resources / prompts rendered through the shared DataTable
// (unified with the MCP-servers, Agents, and audit surfaces): a search box, a
// status filter (all/enabled/disabled), pagination, and a per-row enable
// switch. Tools additionally expose their input_schema as an expandable row
// detail, and a tool whose client-visible name is over 64 characters is flagged
// under its name. The enable/disable mutations keep per-row in-flight state so toggling
// one capability never disables the switches on the others.
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { DataTable, type Column, type FilterDef } from "@/components/DataTable";
import { CodeView } from "@/components/preview/CodeView";
import { CapabilityBulkActions } from "./CapabilityBulkActions";
import { ClientNameFlag, ToggleSwitch } from "./CapabilityRowCells";
import {
  CLIENT_NAME_LIMIT,
  toRows,
  type CapabilityLists,
  type RowDescriptor,
} from "./capabilityRows";

interface Props extends CapabilityLists {
  serverUid: string;
  // Set when the /capabilities fetch failed. An errored fetch yields an
  // undefined list — the same shape as a genuinely empty upstream — so we must
  // distinguish them: a failure shows a load-error message, not "nothing
  // discovered" (which would wrongly imply the upstream has no such capability).
  error?: unknown;
  // Set when the upstream could not be reached and the list was rebuilt from
  // the stored enable/disable rows. Those rows hold no descriptions or schemas,
  // so the parameters are unknown rather than absent — say so, and offer no
  // row detail.
  fromCache?: boolean;
  /** Tools only: calls and errors in the last 24 hours, by original name. */
  usage?: ReadonlyMap<string, { calls: number; errors: number }>;
  /** Tools only: whether each is listed to agents or reached through search. */
  listing?: { listed: ReadonlySet<string>; behind: ReadonlySet<string> } | null;
}

export function CapabilityList(props: Props) {
  const { t } = useTranslation();
  const { serverUid, kind } = props;
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

  const hasSchema = !props.fromCache && rows.some((r) => r.schema);

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
          {row.clientNameLength !== undefined && row.clientNameLength > CLIENT_NAME_LIMIT ? (
            <ClientNameFlag length={row.clientNameLength} />
          ) : null}
          {row.description ? (
            <p className="mt-1 text-sm text-muted-foreground">{row.description}</p>
          ) : null}
        </div>
      ),
    },
    ...(props.listing
      ? [
          {
            key: "listing",
            header: t("mcp.page.colListing"),
            className: "w-32",
            cell: (row: RowDescriptor) =>
              props.listing?.behind.has(row.key) ? (
                <span className="text-xs text-text-muted">{t("mcp.page.behindSearch")}</span>
              ) : props.listing?.listed.has(row.key) ? (
                <span className="text-xs text-text">{t("mcp.page.listed")}</span>
              ) : (
                <span className="text-xs text-text-subtle">—</span>
              ),
          },
        ]
      : []),
    ...(props.usage
      ? [
          {
            key: "calls",
            header: t("mcp.page.colCalls24h"),
            className: "w-24 text-right tabular-nums",
            cell: (row: RowDescriptor) => props.usage?.get(row.key)?.calls ?? 0,
          },
          {
            key: "errors",
            header: t("mcp.page.colErrors"),
            className: "w-20 text-right tabular-nums",
            cell: (row: RowDescriptor) => props.usage?.get(row.key)?.errors ?? 0,
          },
        ]
      : []),
    {
      key: "enabled",
      header: t("mcp.capabilities.header.enabled"),
      className: "w-24 text-right",
      cell: (row) => <ToggleSwitch serverUid={serverUid} kind={kind} row={row} />,
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
    <div className="space-y-3">
      {props.fromCache ? (
        <p className="text-sm text-muted-foreground">{t("mcp.capabilities.fromCache")}</p>
      ) : null}
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
              serverUid={serverUid}
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
                  <div className="px-4 py-3">
                    <CodeView
                      value={JSON.stringify(row.schema, null, 2)}
                      language="json"
                      maxHeight="20rem"
                      lineNumbers={false}
                      ariaLabel={t("mcp.capabilities.schemaLabel")}
                      className="bg-surface-sunken"
                    />
                  </div>
                ) : (
                  <div className="px-4 py-3 text-xs text-muted-foreground">
                    {t("mcp.capabilities.noSchema")}
                  </div>
                )
            : undefined
        }
        emptyMessage={emptyMessage}
      />
    </div>
  );
}
