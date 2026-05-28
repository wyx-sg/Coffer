// frontend/src/components/agents/AgentSkillsTab.tsx
// "Skills" tab on the agent detail page: a "Managed by Coffer" section listing
// the skills Coffer manages FOR this agent (skills whose bindings include this
// agent), rendered through the shared DataTable so it gets search + status
// filter + pagination + select-all + bulk enable/disable + clickable rows
// (→ skill detail). Each row carries an enable/disable Switch wired to the
// per-(skill, agent) mutations. A header-right "Install skills" button opens the
// shared picker dialog bound to this single agent.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";

import { AgentInstallSkillsDialog } from "@/components/agents/AgentInstallSkillsDialog";
import {
  AgentSkillsBulkActions,
  type AgentSkillRow,
} from "@/components/agents/AgentSkillsBulkActions";
import { DataTable, type Column, type FilterDef } from "@/components/DataTable";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import type { AgentOut } from "@/lib/api/agents";
import { useDisableSkill, useEnableSkill, useSkills } from "@/lib/hooks/useSkills";

/** Enable/disable toggle; stops propagation so it doesn't trigger row click. */
function SkillStatusCell({ row, agentName }: { row: AgentSkillRow; agentName: string }) {
  const { t } = useTranslation();
  const enable = useEnableSkill();
  const disable = useDisableSkill();
  return (
    <Switch
      checked={row.binding.enabled}
      onClick={(e) => e.stopPropagation()}
      onCheckedChange={(checked) =>
        (checked ? enable : disable).mutate({
          name: row.skill.name,
          body: { agent_name: agentName },
        })
      }
      disabled={enable.isPending || disable.isPending}
      aria-label={t("agents.skillsTab.toggleAria", { name: row.skill.name })}
    />
  );
}

export function AgentSkillsTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const skills = useSkills();
  const [installOpen, setInstallOpen] = useState(false);

  // The skills Coffer manages for THIS agent are those with a binding whose
  // agent_name matches; carry the binding so the row reflects its enabled state.
  const managed: AgentSkillRow[] = (skills.data ?? []).flatMap((skill) => {
    const binding = skill.bindings.find((b) => b.agent_name === agent.name);
    return binding ? [{ skill, binding }] : [];
  });

  const columns: Column<AgentSkillRow>[] = [
    {
      key: "name",
      header: t("skills.name"),
      className: "whitespace-nowrap",
      cell: (r) => <span className="font-medium">{r.skill.name}</span>,
    },
    {
      key: "description",
      header: t("skills.description"),
      cell: (r) =>
        r.skill.description ? (
          <span className="line-clamp-1 max-w-md text-muted-foreground">{r.skill.description}</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "status",
      header: t("resources.cols.status"),
      className: "text-right",
      cell: (r) => <SkillStatusCell row={r} agentName={agent.name} />,
    },
  ];

  const filters: FilterDef<AgentSkillRow>[] = [
    {
      key: "status",
      label: t("resources.cols.status"),
      allLabel: t("resources.status.all"),
      accessor: (r) => (r.binding.enabled ? "enabled" : "disabled"),
      options: [
        { value: "enabled", label: t("common.enabled") },
        { value: "disabled", label: t("common.disabled") },
      ],
    },
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-muted-foreground">{t("agents.cofferManaged")}</h3>
        <Button size="sm" variant="outline" onClick={() => setInstallOpen(true)}>
          <Plus className="mr-1.5 size-3.5" /> {t("agents.bulkInstallSkills")}
        </Button>
      </div>

      {skills.isPending ? (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : skills.error ? (
        <p className="text-sm text-destructive">{translateApiError(t, skills.error)}</p>
      ) : (
        <DataTable
          rows={managed}
          columns={columns}
          rowKey={(r) => r.skill.name}
          search={{
            accessor: (r) => `${r.skill.name} ${r.skill.description}`,
            placeholder: t("skills.searchPlaceholder"),
          }}
          filters={filters}
          onRowClick={(r) =>
            navigate(`/skills/${r.skill.name}`, {
              state: { backTo: `/agents/${agent.name}`, backLabel: agent.name },
            })
          }
          selection={{
            ariaSelectAll: t("common.bulk.selectAll"),
            ariaSelectRow: (r) => `${t("common.bulk.selectRow")}: ${r.skill.name}`,
            bulkLabel: (count) => t("common.bulk.selected", { count }),
            clearLabel: t("common.clear"),
            renderBulkActions: ({ selectedRows, clear }) => (
              <AgentSkillsBulkActions agentName={agent.name} rows={selectedRows} onDone={clear} />
            ),
          }}
          emptyMessage={t("agents.skillsTab.empty")}
        />
      )}

      <AgentInstallSkillsDialog agents={[agent]} open={installOpen} onOpenChange={setInstallOpen} />
    </div>
  );
}
