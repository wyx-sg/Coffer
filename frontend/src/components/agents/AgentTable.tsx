// frontend/src/components/agents/AgentTable.tsx — the agents list.
// One row per registered coding agent (Claude Code / Codex): product-name
// type, home-relative config dir (full path in a tooltip), whether the agent's
// CLI is actually on this machine (from the turn platform's provider registry),
// delivered Coffer skills, Coffer MCP status, and a delete action.
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AgentBulkActions } from "@/components/agents/AgentBulkActions";
import { AgentMcpStatusBadge } from "@/components/agents/AgentMcpControls";
import { DataTable, type Column } from "@/components/DataTable";
import { RowDeleteButton } from "@/components/table/RowDeleteButton";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { AgentOut } from "@/lib/api/agents";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import { useAgentProviders } from "@/lib/hooks/useAgentProviders";
import { useRemoveAgent } from "@/lib/hooks/useAgents";
import { useSkills } from "@/lib/hooks/useSkills";
import { cn } from "@/lib/utils";

// Managed coding agents only (Claude Code / Codex), keeping this table's
// columns uniform.
type Row = AgentOut;

export function AgentTable({
  agents,
  isLoading = false,
}: {
  agents: AgentOut[];
  /** Skeleton rows while the list resolves — the page keeps its header up. */
  isLoading?: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const remove = useRemoveAgent();
  const skills = useSkills();
  const providers = useAgentProviders();

  const rows: Row[] = agents;
  // Styled confirmation dialog (no native window.confirm). `null` = closed.
  // It holds the ROW: the confirmation names the agent and the request is
  // addressed to its uid.
  const [deleting, setDeleting] = useState<AgentOut | null>(null);

  // Coffer-managed skills currently delivered per agent. A binding row IS a
  // live delivery (the wire drops spent rows), so every row counts. Build the
  // per-agent counts once (single pass over skills × bindings) rather than
  // re-scanning the whole skills list for every agent row on each render.
  // Counted per agent UID: a binding is a pointer at an agent row, and the
  // name beside it on the wire is only what that row is currently called.
  const cofferSkillCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const s of skills.data ?? []) {
      for (const b of s.bindings) {
        counts.set(b.agent_uid, (counts.get(b.agent_uid) ?? 0) + 1);
      }
    }
    return counts;
  }, [skills.data]);

  // Availability by agent type: the provider registry says whether the CLI is
  // on PATH, which is what decides if a chat turn can actually run.
  const availability = useMemo(
    () => new Map((providers.data ?? []).map((p) => [p.agent_key, p.available])),
    [providers.data],
  );

  const columns: Column<Row>[] = [
    {
      key: "name",
      header: t("agents.name"),
      className: "whitespace-nowrap",
      cell: (a) => <span className="font-medium">{a.name}</span>,
    },
    {
      key: "type",
      header: t("agents.type"),
      className: "whitespace-nowrap",
      cell: (a) => <span className="text-muted-foreground">{agentTypeLabel(a.type)}</span>,
    },
    {
      key: "health",
      header: t("agents.cols.health"),
      className: "whitespace-nowrap",
      cell: (a) => {
        if (providers.isPending) return <Skeleton className="h-5 w-20" />;
        const available = availability.get(a.type);
        if (available === undefined) {
          return <span className="text-muted-foreground">{t("common.emptyValue")}</span>;
        }
        return (
          <span
            className={cn(
              "inline-flex items-center rounded-sm px-1.5 py-0.5 text-xs font-medium",
              available ? "bg-status-ok/15 text-status-ok" : "bg-status-err/15 text-status-err",
            )}
          >
            {available ? t("agents.health.available") : t("agents.health.missing")}
          </span>
        );
      },
    },
    {
      key: "config_dir",
      header: t("agents.configDir"),
      cell: (a) => (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="block max-w-44 truncate font-mono text-xs">
              {abbreviateHomePath(a.config_dir)}
            </span>
          </TooltipTrigger>
          <TooltipContent>
            <span className="font-mono">{a.config_dir}</span>
          </TooltipContent>
        </Tooltip>
      ),
    },
    {
      key: "description",
      header: t("agents.description"),
      cell: (a) => (
        <span className="line-clamp-1 max-w-48 text-muted-foreground">
          {a.description || t("common.emptyValue")}
        </span>
      ),
    },
    {
      key: "coffer_skills",
      header: t("agents.cofferSkills"),
      className: "whitespace-nowrap",
      cell: (a) => <Badge variant="secondary">{cofferSkillCounts.get(a.uid) ?? 0}</Badge>,
    },
    {
      key: "mcp",
      header: t("agents.mcp.title"),
      className: "whitespace-nowrap",
      cell: (a) => <AgentMcpStatusBadge uid={a.uid} />,
    },
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (a) => (
        <RowDeleteButton
          ariaLabel={t("agents.deleteAria", { name: a.name })}
          disabled={remove.isPending}
          onDelete={() => setDeleting(a)}
        />
      ),
    },
  ];

  return (
    <>
      <DataTable
        rows={rows}
        isLoading={isLoading}
        columns={columns}
        rowKey={(a) => a.uid}
        search={{
          accessor: (a) => `${a.name} ${agentTypeLabel(a.type)} ${a.config_dir}`,
          placeholder: t("agents.searchPlaceholder"),
        }}
        onRowClick={(a) => navigate(`/agents/${encodeURIComponent(a.uid)}`)}
        selection={{
          ariaSelectAll: t("common.bulk.selectAll"),
          ariaSelectRow: (a) => `${t("common.bulk.selectRow")}: ${a.name}`,
          bulkLabel: (count) => t("common.bulk.selected", { count }),
          clearLabel: t("common.clear"),
          renderBulkActions: ({ selectedRows, clear }) => (
            <AgentBulkActions agents={selectedRows} onDone={clear} />
          ),
        }}
        emptyMessage={t("agents.noMatches")}
      />

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t("agents.removeConfirm", { name: deleting?.name ?? "" })}
        description={t("agents.removeConfirmBody")}
        confirmLabel={remove.isPending ? t("common.deleting") : t("common.delete")}
        pending={remove.isPending}
        onConfirm={() => {
          if (deleting) {
            remove.mutate(deleting.uid, { onSuccess: () => setDeleting(null) });
          }
        }}
      />
    </>
  );
}
