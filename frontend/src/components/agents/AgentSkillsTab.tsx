// frontend/src/components/agents/AgentSkillsTab.tsx
// "Skills" tab on the agent detail page, in the Coffer-managed vs agent's-own
// shape shared with the Memory and MCP tabs:
//
//   • A single card holds the "Follow master library" toggle (agent.follow_all_
//     skills) and, below a divider, the "Managed by Coffer" section it governs.
//   • While following, the reconciler delivers every master skill automatically,
//     so the per-skill managed table would be redundant — the section is the
//     shared "open the Skills page" link (ManagedLinkRow), like the Memory / MCP
//     tabs point at their own pages.
//   • While NOT following, the section is the "Managed by Coffer" DataTable so the
//     user can curate which skills are delivered: search + status filter +
//     pagination + select-all + bulk enable/disable + per-row enable Switch +
//     clickable rows (→ skill detail), plus a header "Install skills" button.
//   • An "Unmanaged skills" section (UnmanagedSkillsSection) listing skills found
//     on disk that Coffer does not manage, with adopt-into-master and delete.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";

import { AgentInstallSkillsDialog } from "@/components/agents/AgentInstallSkillsDialog";
import { ManagedLinkRow } from "@/components/agents/AgentManagedLink";
import {
  AgentSkillsBulkActions,
  type AgentSkillRow,
} from "@/components/agents/AgentSkillsBulkActions";
import { UnmanagedSkillsSection } from "@/components/agents/AgentUnmanagedSkills";
import { DataTable, type Column, type FilterDef } from "@/components/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import type { AgentOut } from "@/lib/api/agents";
import { usePatchAgent } from "@/lib/hooks/useAgents";
import { useDisableSkill, useEnableSkill, useSkills } from "@/lib/hooks/useSkills";

/** Per-row enable/disable toggle for a managed binding; stops propagation so it
 * doesn't trigger the row click. Only rendered while NOT following the master
 * library (in follow mode the managed table is replaced by a link). */
function SkillStatusCell({ row, agent }: { row: AgentSkillRow; agent: AgentOut }) {
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
      accessor: (r) => (r.binding.enabled ? "enabled" : "disabled"),
      options: [
        { value: "enabled", label: t("common.enabled") },
        { value: "disabled", label: t("common.disabled") },
      ],
    },
  ];

  return (
    <div className="space-y-3">
      {/* The "Managed by Coffer" section on top and the follow toggle that
          governs it below, sharing one card split by a divider. */}
      <Card className="divide-y p-0">
        {followAll ? (
          // Following → the reconciler delivers every master skill automatically,
          // so the per-skill managed table is redundant; point at the Skills page
          // (like the Memory / MCP tabs) instead of duplicating it here.
          <div className="p-4">
            <ManagedLinkRow
              title={t("agents.cofferManaged")}
              hint={t("agents.skillsTab.followingManagedHint")}
              buttonLabel={t("agents.skillsTab.openSkillsPage")}
              onOpen={() => navigate("/skills")}
            />
          </div>
        ) : (
          // Not following → curate which skills are delivered to this agent.
          <div className="space-y-3 p-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-muted-foreground">
                {t("agents.cofferManaged")}
              </h3>
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
                    <AgentSkillsBulkActions
                      agentName={agent.name}
                      rows={selectedRows}
                      onDone={clear}
                    />
                  ),
                }}
                emptyMessage={t("agents.skillsTab.empty")}
              />
            )}
          </div>
        )}

        {/* Follow-master-library toggle below the section it governs, in the
            Memory-tab row style: label + second-line help on the left, the
            switch on the far right. */}
        <div className="flex items-start justify-between gap-4 p-4">
          <div className="space-y-1">
            <Label htmlFor="follow-master" className="text-sm font-medium">
              {t("agents.skillsTab.follow")}
            </Label>
            <p className="max-w-prose text-xs text-muted-foreground">
              {t("agents.skillsTab.followHint")}
            </p>
          </div>
          <Switch
            id="follow-master"
            checked={followAll}
            disabled={patchAgent.isPending}
            onCheckedChange={(checked) =>
              patchAgent.mutate({ name: agent.name, body: { follow_all_skills: checked } })
            }
            aria-label={t("agents.skillsTab.follow")}
          />
        </div>
      </Card>

      <UnmanagedSkillsSection agentName={agent.name} />

      <AgentInstallSkillsDialog agents={[agent]} open={installOpen} onOpenChange={setInstallOpen} />
    </div>
  );
}
