import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";

import { AgentMcpStatusBadge } from "@/components/agents/AgentMcpControls";
import { DataTable, type Column, type FilterDef } from "@/components/DataTable";
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

export function AgentTable({ agents }: { agents: AgentOut[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const remove = useRemoveAgent();
  // Styled confirmation dialog (no native window.confirm). `null` = closed.
  const [deletingName, setDeletingName] = useState<string | null>(null);

  const columns: Column<AgentOut>[] = [
    {
      key: "name",
      header: t("agents.name"),
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
      key: "mcp",
      header: t("agents.mcp.title"),
      cell: (a) => <AgentMcpStatusBadge name={a.name} />,
    },
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (a) => (
        <Button
          variant="ghost"
          size="icon"
          className="size-8 text-muted-foreground hover:text-destructive"
          aria-label={t("agents.deleteAria", { name: a.name })}
          disabled={remove.isPending}
          onClick={(e) => {
            e.stopPropagation();
            setDeletingName(a.name);
          }}
        >
          <Trash2 className="size-4" />
        </Button>
      ),
    },
  ];

  const filters: FilterDef<AgentOut>[] = [
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
        rows={agents}
        columns={columns}
        rowKey={(a) => a.name}
        search={{
          accessor: (a) => `${a.name} ${a.type} ${a.config_dir}`,
          placeholder: t("agents.searchPlaceholder"),
        }}
        filters={filters}
        onRowClick={(a) => navigate(`/agents/${a.name}`)}
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
