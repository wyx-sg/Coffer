// frontend/src/kinds/channel/ChannelsTable.tsx
// The channels list rendered via the shared DataTable (mirrors
// KnowledgeBasesTable): rows navigate to the channel detail page; columns show
// the platform type, default agent, enabled state, and a live paired
// indicator fed by each row's /channels/{name}/status query.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { Badge } from "@/components/ui/badge";
import { useChannelStatus } from "@/lib/hooks/useChannels";
import type { ResourceOut } from "@/lib/components/kindRegistry";

function channelTypeOf(row: ResourceOut): string {
  const ct = (row.config as { channel_type?: unknown } | undefined)?.channel_type;
  return typeof ct === "string" ? ct : "telegram";
}

function defaultAgentOf(row: ResourceOut): string {
  const agent = (row.config as { default_agent?: unknown } | undefined)?.default_agent;
  return typeof agent === "string" ? agent : "builtin";
}

/** Live "Paired · <name>" / "Not paired" cell — one status query per row. */
function PairedCell({ name }: { name: string }) {
  const { t } = useTranslation();
  const { data: status } = useChannelStatus(name);
  if (!status) return <span className="text-muted-foreground">—</span>;
  if (status.peer === null) {
    return <span className="text-muted-foreground">{t("channels.notPaired")}</span>;
  }
  return (
    <span className="text-foreground">
      {t("channels.paired")} · {status.peer.display_name}
    </span>
  );
}

export function ChannelsTable({ items }: { items: ResourceOut[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const columns: Column<ResourceOut>[] = [
    {
      key: "name",
      header: t("channels.cols.name"),
      cell: (r) => <span className="font-medium">{r.name}</span>,
    },
    {
      key: "type",
      header: t("channels.cols.type"),
      cell: (r) => {
        const ct = channelTypeOf(r);
        return <Badge variant="secondary">{t(`channels.types.${ct}`, ct)}</Badge>;
      },
    },
    {
      key: "agent",
      header: t("channels.cols.agent"),
      cell: (r) => <span className="text-muted-foreground">{defaultAgentOf(r)}</span>,
    },
    {
      key: "state",
      header: t("channels.cols.state"),
      cell: (r) =>
        r.enabled ? (
          <Badge>{t("common.enabled")}</Badge>
        ) : (
          <Badge variant="outline">{t("common.disabled")}</Badge>
        ),
    },
    {
      key: "paired",
      header: t("channels.cols.paired"),
      cell: (r) => <PairedCell name={r.name} />,
    },
  ];

  return (
    <DataTable
      rows={items}
      columns={columns}
      rowKey={(r) => r.name}
      search={{
        accessor: (r) => `${r.name} ${channelTypeOf(r)}`,
        placeholder: t("channels.searchPlaceholder"),
      }}
      onRowClick={(r) => navigate(`/channels/${r.name}`)}
      emptyMessage={t("channels.noMatches")}
    />
  );
}
