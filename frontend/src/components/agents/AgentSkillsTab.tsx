// frontend/src/components/agents/AgentSkillsTab.tsx
// "Skills" tab on the agent detail page — the same shape as the MCP servers
// tab, and for the same reason: delivery has exactly ONE control now, and it
// lives on the skill, not on the agent. A skill reaches an agent iff the skill
// is enabled AND the agent falls inside the skill's scope, both of which are
// edited on the Skill page. So this tab manages nothing Coffer-side; it points
// at that page and then shows what the rule currently produces:
//
//   1. A "Managed by Coffer" pointer row (the shared ManagedLinkRow) whose hint
//      says where delivery is decided, with a button to the Skills page.
//   2. A READ-ONLY table of the skills currently delivered to THIS agent —
//      every skill carrying a binding for it, name + description, the
//      copy_fallback "Copied" badge, rows clicking through to the skill detail
//      page. No per-row switch, no status filter, no selection, no Install:
//      there is nothing here to decide.
//   3. An "Unmanaged skills" section (UnmanagedSkillsSection) listing skills
//      found on disk that Coffer does not manage, with open-folder, adopt and
//      delete.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ManagedLinkRow } from "@/components/agents/AgentManagedLink";
import { UnmanagedSkillsSection } from "@/components/agents/AgentUnmanagedSkills";
import { DataTable, type Column } from "@/components/DataTable";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import type { AgentOut } from "@/lib/api/agents";
import type { SkillBindingOut, SkillOut } from "@/lib/api/skills";
import { useSkills } from "@/lib/hooks/useSkills";

interface DeliveredSkillRow {
  skill: SkillOut;
  binding: SkillBindingOut;
}

export function AgentSkillsTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const skills = useSkills();

  // The skills delivered to THIS agent are those carrying a binding for it —
  // the wire only reports live deliveries, so the binding's presence is the
  // whole answer. The binding still rides along for the link-mode badge.
  const delivered: DeliveredSkillRow[] = (skills.data ?? []).flatMap((skill) => {
    const binding = skill.bindings.find((b) => b.agent_name === agent.name);
    return binding ? [{ skill, binding }] : [];
  });

  const columns: Column<DeliveredSkillRow>[] = [
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
  ];

  return (
    <div className="space-y-3">
      {/* One card: the pointer at the Skills page (where delivery is decided)
          and, under it, the read-only list of what that decision delivered. */}
      <Card className="space-y-3 p-4">
        <div data-testid="skills-managed-header">
          <ManagedLinkRow
            title={t("agents.cofferManaged")}
            hint={t("agents.skillsTab.managedHint")}
            buttonLabel={t("agents.skillsTab.openSkillsPage")}
            onOpen={() => navigate("/skills")}
          />
        </div>

        {skills.isPending ? (
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : skills.error ? (
          <p className="text-sm text-destructive">{translateApiError(t, skills.error)}</p>
        ) : (
          <DataTable
            rows={delivered}
            columns={columns}
            rowKey={(r) => r.skill.name}
            search={{
              accessor: (r) => `${r.skill.name} ${r.skill.description}`,
              placeholder: t("skills.searchPlaceholder"),
            }}
            onRowClick={(r) =>
              navigate(`/skills/${r.skill.name}`, {
                state: { backTo: `/agents/${agent.name}`, backLabel: agent.name },
              })
            }
            emptyMessage={t("agents.skillsTab.empty")}
          />
        )}
      </Card>

      <UnmanagedSkillsSection agentName={agent.name} />
    </div>
  );
}
