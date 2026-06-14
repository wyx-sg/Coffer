import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";

import { AgentBulkActions } from "@/components/agents/AgentBulkActions";
import { AgentMcpStatusBadge } from "@/components/agents/AgentMcpControls";
import { DataTable, type Column, type FilterDef } from "@/components/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { AgentOut } from "@/lib/api/agents";
import { useRemoveAgent } from "@/lib/hooks/useAgents";
import { useSkills } from "@/lib/hooks/useSkills";

// Managed coding agents only (Claude Code / Codex), keeping this table's
// columns uniform.
type Row = AgentOut;

export function AgentTable({ agents }: { agents: AgentOut[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const remove = useRemoveAgent();
  const skills = useSkills();

  const rows: Row[] = agents;
  // Styled confirmation dialog (no native window.confirm). `null` = closed.
  const [deletingName, setDeletingName] = useState<string | null>(null);

  // Coffer-managed skills currently installed (enabled binding) per agent.
  // Build the per-agent counts once (single pass over skills × bindings) rather
  // than re-scanning the whole skills list for every agent row on each render.
  const cofferSkillCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const s of skills.data ?? []) {
      for (const b of s.bindings) {
        if (b.enabled) counts.set(b.agent_name, (counts.get(b.agent_name) ?? 0) + 1);
      }
    }
    return counts;
  }, [skills.data]);

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
      cell: (a) => <span className="text-muted-foreground">{a.type}</span>,
    },
    {
      key: "config_dir",
      header: t("agents.configDir"),
      cell: (a) => <span className="font-mono text-xs">{a.config_dir}</span>,
    },
    {
      key: "description",
      header: t("agents.description"),
      cell: (a) => (
        <span className="line-clamp-1 max-w-xs text-muted-foreground">{a.description || "—"}</span>
      ),
    },
    {
      key: "coffer_skills",
      header: t("agents.cofferSkills"),
      className: "whitespace-nowrap",
      cell: (a) => <Badge variant="secondary">{cofferSkillCounts.get(a.name) ?? 0}</Badge>,
    },
    {
      key: "mcp",
      header: t("agents.mcp.title"),
      className: "whitespace-nowrap",
      cell: (a) => <AgentMcpStatusBadge name={a.name} />,
    },
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (a) => (
        <Button
          variant="ghost"
          size="sm"
          className="text-muted-foreground hover:text-destructive"
          aria-label={t("agents.deleteAria", { name: a.name })}
          disabled={remove.isPending}
          onClick={(e) => {
            e.stopPropagation();
            setDeletingName(a.name);
          }}
        >
          <Trash2 className="mr-1.5 size-3.5" /> {t("common.delete")}
        </Button>
      ),
    },
  ];

  const filters: FilterDef<Row>[] = [
    {
      key: "type",
      label: t("agents.type"),
      allLabel: t("agents.allTypes"),
      accessor: (a) => a.type,
      options: [
        { value: "claude_code", label: "claude_code" },
        { value: "codex", label: "codex" },
      ],
    },
  ];

  return (
    <>
      <DataTable
        rows={rows}
        columns={columns}
        rowKey={(a) => a.name}
        search={{
          accessor: (a) => `${a.name} ${a.type} ${a.config_dir}`,
          placeholder: t("agents.searchPlaceholder"),
        }}
        filters={filters}
        onRowClick={(a) => navigate(`/agents/${a.name}`)}
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

      <Dialog open={deletingName !== null} onOpenChange={(o) => !o && setDeletingName(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("agents.removeConfirm", { name: deletingName ?? "" })}</DialogTitle>
            <DialogDescription>{t("agents.removeConfirmBody")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeletingName(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() => {
                if (deletingName) {
                  remove.mutate(deletingName, { onSuccess: () => setDeletingName(null) });
                }
              }}
            >
              {remove.isPending ? t("common.deleting") : t("common.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
