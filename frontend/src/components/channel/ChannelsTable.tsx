// frontend/src/components/channel/ChannelsTable.tsx
// The channels list rendered via the shared DataTable: rows navigate to the
// channel detail page; columns show the platform type, default agent, live
// runtime health, the machine the channel is bound to, a live paired
// indicator, the reach control, and a delete action. The health cell mirrors
// the MCP-server surface's ServerHealthCell / HealthBadge, sharing the
// statusColors vocabulary so the two never drift.
//
// Health and "Runs on" are neighbours on purpose: "Stopped" means one thing on
// the bound machine (a fault) and another on every other machine holding the
// same channel (the system working), and the column beside it is what tells
// them apart. "Runs on" is a different question from Reach and carries its own
// header — reach is which AGENTS the channel may drive, and merging the two
// labels would make one column claim to answer both.
//
// The reach column used to be a static Enabled/Disabled Badge — a fact the user
// could read but not act on, in the one column every other list makes the
// control. It is now the same ScopeControl every other kind's row carries,
// reading its value from `ResourceOut.scope` on the list payload so the list
// still costs one request rather than one per row — and the same three-state
// reach filter every scoped list offers sits in the toolbar above it.
//
// The per-row cells that fetch their own status — health, "Runs on", paired —
// live in `ChannelRowCells.tsx`; this file is the columns and the table.
//
// Delete was missing entirely: a channel could be registered from this page but
// only removed from its detail page. It is the shared row delete now, with the
// confirmation hoisted to table level so closing it can't fall through to the
// row's navigation.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { BulkReachActions } from "@/components/reach/BulkReachActions";
import { ScopeControl } from "@/components/ScopeControl";
import { BulkDeleteButton } from "@/components/table/BulkDeleteButton";
import { RowDeleteButton } from "@/components/table/RowDeleteButton";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { resourcesApi } from "@/lib/api/resources";
import { resourcesKey } from "@/lib/api/queryKeys";
import { useAgentProviders } from "@/lib/hooks/useAgentProviders";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";
import { CHANNEL_KIND } from "@/lib/hooks/useChannels";
import { useDeleteResource } from "@/lib/hooks/useResourceMutations";
import { reachFilter } from "@/lib/reachFilter";
import type { ResourceOut } from "@/lib/api/resources";
import { agentDisplayName } from "./agentLabels";
import { HealthCell, MachineCell, PairedCell } from "./ChannelRowCells";

/** The row's platform. Defaults to telegram: a channel config without a type
 *  cannot exist on the wire, and guessing beats rendering an empty cell. */
function channelTypeOf(row: ResourceOut): string {
  const ct = (row.config as { channel_type?: unknown } | undefined)?.channel_type;
  return typeof ct === "string" ? ct : "telegram";
}

/** The bound agent's provider key, or null when the config names none. */
function defaultAgentOf(row: ResourceOut): string | null {
  const agent = (row.config as { default_agent?: unknown } | undefined)?.default_agent;
  return typeof agent === "string" && agent.length > 0 ? agent : null;
}

export function ChannelsTable({
  items,
  isLoading = false,
}: {
  items: ResourceOut[];
  isLoading?: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const del = useDeleteResource();
  const [deletingName, setDeletingName] = useState<string | null>(null);
  const bulk = useBulkMutate({ invalidate: [resourcesKey] });
  // Display names for the bound-agent column; one cached query, shared with
  // the edit dialog's picker.
  const { data: agents } = useAgentProviders();

  const columns: Column<ResourceOut>[] = [
    {
      key: "name",
      header: t("channels.cols.name"),
      className: "whitespace-nowrap",
      cell: (r) => <span className="font-medium">{r.name}</span>,
    },
    {
      key: "type",
      header: t("channels.cols.type"),
      className: "whitespace-nowrap",
      cell: (r) => {
        const ct = channelTypeOf(r);
        return <Badge variant="secondary">{t(`channels.types.${ct}`, ct)}</Badge>;
      },
    },
    {
      key: "agent",
      header: t("channels.cols.agent"),
      className: "w-full min-w-[12rem]",
      cell: (r) => {
        const agent = defaultAgentOf(r);
        return (
          <span className="text-muted-foreground">
            {agent === null ? t("common.emptyValue") : agentDisplayName(agent, agents)}
          </span>
        );
      },
    },
    {
      key: "health",
      header: t("channels.cols.health"),
      className: "whitespace-nowrap",
      cell: (r) => <HealthCell name={r.name} />,
    },
    {
      key: "runs-on",
      header: t("channels.cols.runsOn"),
      className: "whitespace-nowrap",
      cell: (r) => (
        // Like the reach cell, the control must not fall through to the row's
        // navigation — opening a picker is not a request to leave the page.
        <div onClick={(e) => e.stopPropagation()}>
          <MachineCell row={r} />
        </div>
      ),
    },
    {
      key: "paired",
      header: t("channels.cols.paired"),
      className: "whitespace-nowrap",
      cell: (r) => <PairedCell name={r.name} />,
    },
    {
      key: "reach",
      header: t("resources.cols.reach"),
      className: "whitespace-nowrap text-right",
      cell: (r) => (
        <div className="flex justify-end" onClick={(e) => e.stopPropagation()}>
          <ScopeControl
            kind={CHANNEL_KIND}
            name={r.name}
            enabled={r.enabled}
            scope={r.scope ?? null}
          />
        </div>
      ),
    },
    {
      key: "actions",
      header: "",
      className: "whitespace-nowrap text-right",
      cell: (r) => (
        <RowDeleteButton
          ariaLabel={`${t("channels.deleteTitle")}: ${r.name}`}
          onDelete={() => setDeletingName(r.name)}
        />
      ),
    },
  ];

  return (
    <>
      <DataTable
        rows={items}
        isLoading={isLoading}
        columns={columns}
        rowKey={(r) => r.name}
        search={{
          accessor: (r) => `${r.name} ${channelTypeOf(r)}`,
          placeholder: t("channels.searchPlaceholder"),
        }}
        filters={[reachFilter<ResourceOut>(t, (r) => ({ enabled: r.enabled, scope: r.scope }))]}
        onRowClick={(r) => navigate(`/channels/${r.name}`)}
        selection={{
          ariaSelectAll: t("common.bulk.selectAll"),
          ariaSelectRow: (r) => `${t("common.bulk.selectRow")}: ${r.name}`,
          bulkLabel: (count) => t("common.bulk.selected", { count }),
          clearLabel: t("common.clear"),
          renderBulkActions: ({ selectedRows, clear }) => (
            <>
              <BulkReachActions
                rows={selectedRows.map((r) => ({ kind: CHANNEL_KIND, name: r.name }))}
                onDone={clear}
              />
              <BulkDeleteButton
                title={t("channels.deleteTitle")}
                description={t("channels.bulkDeleteConfirm", { count: selectedRows.length })}
                pending={bulk.isPending}
                onConfirm={async () => {
                  await bulk.run(selectedRows, (r) => resourcesApi.remove(CHANNEL_KIND, r.name));
                  clear();
                }}
              />
            </>
          ),
        }}
        emptyMessage={t("channels.noMatches")}
      />

      <ConfirmDialog
        open={deletingName !== null}
        onOpenChange={(open) => {
          if (!open) setDeletingName(null);
        }}
        title={t("channels.deleteTitle")}
        description={t("channels.deleteConfirm", { name: deletingName ?? "" })}
        confirmLabel={t("common.delete")}
        pending={del.isPending}
        onConfirm={() => {
          const name = deletingName;
          setDeletingName(null);
          if (name !== null) del.mutate({ kind: CHANNEL_KIND, name });
        }}
      />
    </>
  );
}
