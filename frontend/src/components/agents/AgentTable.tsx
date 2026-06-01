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
import type { BuiltinAgentOut } from "@/lib/api/builtinAgents";
import { translateApiError } from "@/lib/api/errors";
import { useRemoveAgent } from "@/lib/hooks/useAgents";
import { useRemoveBuiltinAgent } from "@/lib/hooks/useBuiltinAgents";
import { useSkills } from "@/lib/hooks/useSkills";

// One table, two kinds of row. External agents (kind `agent`) navigate to
// `/agents/{name}` and own MCP/skill columns; built-in agents (kind
// `builtin_agent`) navigate to `/agents/builtin/{name}` and intentionally skip
// the MCP/skills cells — those query external-agent endpoints that would 404.
type Row =
  | ({ kind: "agent" } & AgentOut)
  | { kind: "builtin_agent"; name: string; builtin: BuiltinAgentOut };

export function AgentTable({
  agents,
  builtinAgents = [],
}: {
  agents: AgentOut[];
  builtinAgents?: BuiltinAgentOut[];
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const remove = useRemoveAgent();
  const removeBuiltin = useRemoveBuiltinAgent();
  const skills = useSkills();
  // Styled confirmation dialog (no native window.confirm). `null` = closed.
  const [deleting, setDeleting] = useState<Row | null>(null);
  // Built-in delete may 409 (CANNOT_DELETE_LAST_BUILTIN_AGENT) — shown inline.
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Merge both kinds into one row list: built-ins first, then external agents.
  const rows: Row[] = useMemo(
    () => [
      ...builtinAgents.map((b): Row => ({ kind: "builtin_agent", name: b.name, builtin: b })),
      ...agents.map((a): Row => ({ kind: "agent", ...a })),
    ],
    [agents, builtinAgents],
  );

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

  const dash = <span className="text-muted-foreground">—</span>;

  const columns: Column<Row>[] = [
    {
      key: "name",
      header: t("agents.name"),
      className: "whitespace-nowrap",
      cell: (r) => <span className="font-medium">{r.name}</span>,
    },
    {
      key: "type",
      header: t("agents.type"),
      cell: (r) =>
        r.kind === "builtin_agent" ? (
          <Badge variant="secondary">{t("agents.typeBuiltin")}</Badge>
        ) : (
          <span className="text-muted-foreground">{r.type}</span>
        ),
    },
    {
      key: "config_dir",
      header: t("agents.configDir"),
      cell: (r) =>
        r.kind === "agent" ? <span className="font-mono text-xs">{r.config_dir}</span> : dash,
    },
    {
      key: "description",
      header: t("agents.description"),
      cell: (r) => {
        const text =
          r.kind === "agent"
            ? r.description
            : (r.builtin.description ?? r.builtin.config.model ?? null);
        return text ? (
          <span className="line-clamp-1 max-w-xs text-muted-foreground">{text}</span>
        ) : (
          dash
        );
      },
    },
    {
      key: "coffer_skills",
      header: t("agents.cofferSkills"),
      className: "whitespace-nowrap",
      // Skills are only meaningful for external agents — built-in rows show "—".
      cell: (r) =>
        r.kind === "agent" ? (
          <Badge variant="secondary">{cofferSkillCounts.get(r.name) ?? 0}</Badge>
        ) : (
          dash
        ),
    },
    {
      key: "mcp",
      header: t("agents.mcp.title"),
      className: "whitespace-nowrap",
      // The MCP badge queries /agents/{name}/mcp-install — only valid for
      // external agents; built-in rows must not render it (it would 404).
      cell: (r) => (r.kind === "agent" ? <AgentMcpStatusBadge name={r.name} /> : dash),
    },
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (r) => (
        <Button
          variant="ghost"
          size="sm"
          className="text-muted-foreground hover:text-destructive"
          aria-label={t("agents.deleteAria", { name: r.name })}
          disabled={remove.isPending || removeBuiltin.isPending}
          onClick={(e) => {
            e.stopPropagation();
            setDeleteError(null);
            setDeleting(r);
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
      accessor: (r) => (r.kind === "builtin_agent" ? "builtin" : r.type),
      options: [
        { value: "builtin", label: t("agents.typeBuiltin") },
        { value: "claude_code", label: "claude_code" },
        { value: "codex", label: "codex" },
      ],
    },
  ];

  const deletePending = remove.isPending || removeBuiltin.isPending;

  const confirmDelete = () => {
    if (!deleting) return;
    if (deleting.kind === "builtin_agent") {
      removeBuiltin.mutate(deleting.name, {
        onSuccess: () => {
          setDeleting(null);
          setDeleteError(null);
        },
        onError: (err) => setDeleteError(translateApiError(t, err)),
      });
    } else {
      remove.mutate(deleting.name, { onSuccess: () => setDeleting(null) });
    }
  };

  return (
    <>
      <DataTable
        rows={rows}
        columns={columns}
        rowKey={(r) => `${r.kind}:${r.name}`}
        search={{
          accessor: (r) =>
            r.kind === "agent"
              ? `${r.name} ${r.type} ${r.config_dir}`
              : `${r.name} builtin ${r.builtin.config.model}`,
          placeholder: t("agents.searchPlaceholder"),
        }}
        filters={filters}
        onRowClick={(r) => {
          if (r.kind === "builtin_agent") navigate(`/agents/builtin/${r.name}`);
          else navigate(`/agents/${r.name}`);
        }}
        selection={{
          ariaSelectAll: t("common.bulk.selectAll"),
          ariaSelectRow: (r) => `${t("common.bulk.selectRow")}: ${r.name}`,
          bulkLabel: (count) => t("common.bulk.selected", { count }),
          clearLabel: t("common.clear"),
          // Bulk actions only apply to external agents — built-in rows are
          // filtered out so the install/skills mutations never target them.
          renderBulkActions: ({ selectedRows, clear }) => (
            <AgentBulkActions
              agents={selectedRows.filter((r) => r.kind === "agent")}
              onDone={clear}
            />
          ),
        }}
        emptyMessage={t("agents.noMatches")}
      />

      <Dialog
        open={deleting !== null}
        onOpenChange={(o) => {
          if (!o) {
            setDeleting(null);
            setDeleteError(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {deleting?.kind === "builtin_agent"
                ? t("builtinAgents.removeConfirm", { name: deleting?.name ?? "" })
                : t("agents.removeConfirm", { name: deleting?.name ?? "" })}
            </DialogTitle>
            <DialogDescription>
              {deleting?.kind === "builtin_agent"
                ? t("builtinAgents.removeConfirmBody")
                : t("agents.removeConfirmBody")}
            </DialogDescription>
          </DialogHeader>
          {deleteError ? (
            <p className="text-sm text-destructive" role="alert">
              {deleteError}
            </p>
          ) : null}
          <DialogFooter>
            <Button
              variant="ghost"
              onClick={() => {
                setDeleting(null);
                setDeleteError(null);
              }}
            >
              {t("common.cancel")}
            </Button>
            <Button variant="destructive" disabled={deletePending} onClick={confirmDelete}>
              {deletePending ? t("common.deleting") : t("common.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
