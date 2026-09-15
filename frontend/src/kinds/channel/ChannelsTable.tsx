// frontend/src/kinds/channel/ChannelsTable.tsx
// The channels list rendered via the shared DataTable: rows navigate to the
// channel detail page; columns show the platform type, default agent, live
// runtime health, a live paired indicator, the reach control, and a delete
// action. The health cell mirrors the MCP-server surface's ServerHealthCell /
// HealthBadge, sharing the statusColors vocabulary so the two never drift.
//
// The reach column used to be a static Enabled/Disabled Badge — a fact the user
// could read but not act on, in the one column every other list makes the
// control. It is now the same ScopeControl every other kind's row carries,
// reading its value from `ResourceOut.scope` on the list payload so the list
// still costs one request rather than one per row — and the same three-state
// reach filter every scoped list offers sits in the toolbar above it.
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
import { useAgentProviders } from "@/lib/hooks/useAgentProviders";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";
import { useChannelStatus, CHANNEL_KIND } from "@/lib/hooks/useChannels";
import { useDeleteResource } from "@/lib/hooks/useResourceMutations";
import { reachFilter } from "@/lib/reachFilter";
import { cn } from "@/lib/utils";
import type { ResourceOut } from "@/lib/components/kindRegistry";
import { agentDisplayName } from "./agentLabels";
import { channelHealthClass } from "./channelHealth";

function channelTypeOf(row: ResourceOut): string {
  const ct = (row.config as { channel_type?: unknown } | undefined)?.channel_type;
  return typeof ct === "string" ? ct : "telegram";
}

/** The bound agent's provider key, or null when the config names none. */
function defaultAgentOf(row: ResourceOut): string | null {
  const agent = (row.config as { default_agent?: unknown } | undefined)?.default_agent;
  return typeof agent === "string" && agent.length > 0 ? agent : null;
}

/**
 * Live runtime health cell — the adapter `running` state from the same cached
 * /channels/{name}/status query the PairedCell uses. Mirrors the MCP-server
 * surface's ServerHealthCell/HealthBadge: an outline Badge on the shared
 * status tokens, through the one running/stopped tone mapping the detail
 * page's Status card uses too (running -> ok, stopped -> warn).
 */
function HealthCell({ name }: { name: string }) {
  const { t } = useTranslation();
  const { data: status } = useChannelStatus(name);
  if (!status) return <span className="text-muted-foreground">{t("common.emptyValue")}</span>;
  return (
    <Badge
      variant="outline"
      className={cn("whitespace-nowrap border-transparent", channelHealthClass(status.running))}
      data-testid="channel-health-badge"
    >
      {status.running ? t("channels.status.running") : t("channels.status.stopped")}
    </Badge>
  );
}

/** Live "Paired · <name>" / "Not paired" cell — one status query per row. */
function PairedCell({ name }: { name: string }) {
  const { t } = useTranslation();
  const { data: status } = useChannelStatus(name);
  if (!status) return <span className="text-muted-foreground">{t("common.emptyValue")}</span>;
  if (status.peer === null) {
    return <span className="text-muted-foreground">{t("channels.notPaired")}</span>;
  }
  return (
    <span className="text-foreground">
      {t("channels.paired")} · {status.peer.display_name}
    </span>
  );
}

export function ChannelsTable({
  items,
  isLoading = false,
}: {
  items: ResourceOut[];
  /** Skeleton rows while the list resolves — the page keeps its header up. */
  isLoading?: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const del = useDeleteResource();
  const [deletingName, setDeletingName] = useState<string | null>(null);
  const bulk = useBulkMutate({ invalidate: [["resources"]] });
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
