// frontend/src/components/agents/AgentSkillsTab.tsx
// "Skills" tab on the agent detail page — the same shape as the MCP servers
// tab, and for the same reason: delivery has exactly ONE control now, and it
// lives on the skill, not on the agent. A skill reaches an agent iff the skill
// is enabled AND the agent falls inside the skill's scope, both of which are
// edited on the Skill page. So this tab manages nothing Coffer-side:
//
//   1. A "Managed by Coffer" pointer row (the shared ManagedLinkRow) whose hint
//      says where delivery is decided, with a button to the Skills page. It
//      used to carry a read-only copy of the delivered skills underneath, but
//      that table decided nothing and duplicated the Skills page — the page it
//      already points at — so it's gone; the button is the whole answer.
//   2. An "Unmanaged skills" section (UnmanagedSkillsSection) listing skills
//      found on disk that Coffer does not manage, with open-folder, adopt and
//      delete. That one stays: those skills exist nowhere else in the UI.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ManagedLinkRow } from "@/components/agents/AgentManagedLink";
import { UnmanagedSkillsSection } from "@/components/agents/AgentUnmanagedSkills";
import { Card } from "@/components/ui/card";
import type { AgentOut } from "@/lib/api/agents";

export function AgentSkillsTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <div className="space-y-3">
      <Card className="p-4">
        <div data-testid="skills-managed-header">
          <ManagedLinkRow
            title={t("agents.cofferManaged")}
            hint={t("agents.skillsTab.managedHint")}
            buttonLabel={t("agents.skillsTab.openSkillsPage")}
            onOpen={() => navigate("/skills")}
          />
        </div>
      </Card>

      <UnmanagedSkillsSection agentName={agent.name} />
    </div>
  );
}
