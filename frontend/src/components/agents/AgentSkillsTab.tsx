// frontend/src/components/agents/AgentSkillsTab.tsx
// "Skills" tab on the agent detail page: a "Managed by Coffer" section listing
// the skills Coffer manages FOR this agent (skills whose bindings include this
// agent), rendered through the shared DataTable so it gets search + status
// filter + pagination + select-all + bulk enable/disable + clickable rows
// (→ skill detail). Each row carries an enable/disable Switch wired to the
// per-(skill, agent) mutations. A header-right "Install skills" button opens the
// shared picker dialog bound to this single agent.
//
// Spec 005 FR-025 additions:
//   • A "Follow master library" switch (agent.follow_all_skills). While ON, the
//     backend reconciler delivers every master skill automatically and the
//     per-skill Switches become EXCLUSION toggles (PATCH skill_exclusions)
//     rather than binding enable/disable calls.
//   • An "Unmanaged skills" section (UnmanagedSkillsSection, extracted to
//     AgentUnmanagedSkills.tsx) listing skills found on disk that Coffer
//     does not manage, with adopt-into-master and delete actions.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";

import { AgentInstallSkillsDialog } from "@/components/agents/AgentInstallSkillsDialog";
import {
  AgentSkillsBulkActions,
  type AgentSkillRow,
} from "@/components/agents/AgentSkillsBulkActions";
import { UnmanagedSkillsSection } from "@/components/agents/AgentUnmanagedSkills";
import { DataTable, type Column, type FilterDef } from "@/components/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import type { AgentOut } from "@/lib/api/agents";
import { usePatchAgent } from "@/lib/hooks/useAgents";
import { useDisableSkill, useEnableSkill, useSkills } from "@/lib/hooks/useSkills";

/** Enable/disable toggle; stops propagation so it doesn't trigger row click.
 * In follow-all mode the switch edits the agent's exclusion list instead of
 * the binding (the backend reconciler owns delivery while following). */
function SkillStatusCell({ row, agent }: { row: AgentSkillRow; agent: AgentOut }) {
  const { t } = useTranslation();
  const enable = useEnableSkill();
  const disable = useDisableSkill();
  const patchAgent = usePatchAgent();

  const followAll = agent.follow_all_skills ?? false;
  const exclusions = agent.skill_exclusions ?? [];

  if (followAll) {
    const excluded = exclusions.includes(row.skill.name);
    return (
      <Switch
        checked={!excluded}
        title={t("agents.skillsTab.excludeHint")}
        onClick={(e) => e.stopPropagation()}
        onCheckedChange={(checked) =>
          patchAgent.mutate({
            name: agent.name,
            body: {
              skill_exclusions: checked
                ? exclusions.filter((n) => n !== row.skill.name)
                : [...exclusions, row.skill.name],
            },
          })
        }
        disabled={patchAgent.isPending}
        aria-label={t("agents.skillsTab.toggleAria", { name: row.skill.name })}
      />
    );
  }

  return (
    <Switch
      checked={row.binding.enabled}
      onClick={(e) => e.stopPropagation()}
      onCheckedChange={(checked) =>
        (checked ? enable : disable).mutate({
          name: row.skill.name,
          body: { agent_name: agent.name },
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
  const patchAgent = usePatchAgent();
  const [installOpen, setInstallOpen] = useState(false);

  const followAll = agent.follow_all_skills ?? false;
  const exclusions = agent.skill_exclusions ?? [];

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
      cell: (r) => (
        <span className="flex items-center gap-2">
          <span className="font-medium">{r.skill.name}</span>
          {r.binding.link_mode === "copy_fallback" && (
            <Badge
              variant="outline"
              data-testid="skill-degraded-badge"
              className="border-amber-500/50 text-amber-600 dark:text-amber-400"
              title={t("agents.skillsTab.degradedTooltip")}
            >
              {t("agents.skillsTab.degradedBadge")}
            </Badge>
          )}
        </span>
      ),
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
      cell: (r) => <SkillStatusCell row={r} agent={agent} />,
    },
  ];

  const filters: FilterDef<AgentSkillRow>[] = [
    {
      key: "status",
      label: t("resources.cols.status"),
      allLabel: t("resources.status.all"),
      // In follow mode "enabled" means "not excluded" — the reconciler delivers
      // everything except the exclusion list, regardless of binding state.
      accessor: (r) =>
        (followAll ? !exclusions.includes(r.skill.name) : r.binding.enabled)
          ? "enabled"
          : "disabled",
      options: [
        { value: "enabled", label: t("common.enabled") },
        { value: "disabled", label: t("common.disabled") },
      ],
    },
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-4 rounded-md border px-3 py-2">
        <div className="min-w-0">
          <p className="text-sm font-medium">{t("agents.skillsTab.follow")}</p>
          <p className="text-xs text-muted-foreground">{t("agents.skillsTab.followHint")}</p>
        </div>
        <Switch
          checked={followAll}
          disabled={patchAgent.isPending}
          onCheckedChange={(checked) =>
            patchAgent.mutate({ name: agent.name, body: { follow_all_skills: checked } })
          }
          aria-label={t("agents.skillsTab.follow")}
        />
      </div>

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
          // In follow mode the reconciler owns delivery — bulk binding
          // mutations would silently fight it, so selection is hidden.
          selection={
            followAll
              ? undefined
              : {
                  ariaSelectAll: t("common.bulk.selectAll"),
                  ariaSelectRow: (r) => `${t("common.bulk.selectRow")}: ${r.skill.name}`,
                  bulkLabel: (count) => t("common.bulk.selected", { count }),
                  clearLabel: t("common.clear"),
                  renderBulkActions: ({ selectedRows, clear }) => (
                    <AgentSkillsBulkActions
                      agentName={agent.name}
                      rows={selectedRows}
                      onDone={clear}
                    />
                  ),
                }
          }
          emptyMessage={t("agents.skillsTab.empty")}
        />
      )}

      <UnmanagedSkillsSection agentName={agent.name} />

      <AgentInstallSkillsDialog agents={[agent]} open={installOpen} onOpenChange={setInstallOpen} />
    </div>
  );
}
