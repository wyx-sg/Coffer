// src/components/agents/detail/AgentDetailTabs.tsx — the agent page's nine tabs, each at its own path.
//
// Overview · Model · Skills · MCP servers · Plugins · Hooks · Memory · Sessions · Config files ·
// Memory · Sessions (spec agent-registry "Expose every agent operation
// through REST, CLI and the Agents page"). The open tab is the path segment (`useDetailTab`); only the open
// tab is mounted, so a tab reads its data when it is opened. Labels carry no counts. Leaving Config
// files with an unsaved draft asks first, through the shell's unsaved-changes
// guard, like every other way out of an editor.
import { useTranslation } from "react-i18next";

import { AgentConfigFilesTab } from "@/components/agents/AgentConfigFilesTab";
import { AgentHooksTab } from "@/components/agents/AgentHooksTab";
import { AgentPluginsTab } from "@/components/agents/AgentPluginsTab";
import { AgentMcpServersTab } from "@/components/agents/AgentMcpServersTab";
import { AgentMemoryTab } from "@/components/agents/AgentMemoryTab";
import { AgentOverviewTab } from "@/components/agents/AgentOverviewTab";
import { AgentSkillsTab } from "@/components/agents/AgentSkillsTab";
import type { useAgentRowActions } from "@/components/agents/list/useAgentRowActions";
import { AgentModelTab } from "@/components/agents/model/AgentModelTab";
import { AgentSessionsTab } from "@/components/agents/sessions/AgentSessionsTab";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AGENT_TABS, agentBasePath, DEFAULT_AGENT_TAB, type AgentTab } from "@/lib/agents/routes";
import type { AgentOut, AgentTypeOut } from "@/lib/api/agents";
import { useDetailTab } from "@/lib/detailTabs";
import { useFeatureEnabled } from "@/lib/hooks/useFeatures";

interface Props {
  agent: AgentOut;
  typeRow: AgentTypeOut;
  rowActions: ReturnType<typeof useAgentRowActions>;
}

const LABEL_KEY: Record<AgentTab, string> = {
  overview: "agents.tabs.overview",
  model: "agents.tabs.model",
  skills: "agents.tabs.skills",
  "mcp-servers": "agents.tabs.mcpServers",
  plugins: "agents.tabs.plugins",
  hooks: "agents.tabs.hooks",
  config: "agents.tabs.config",
  memory: "agents.tabs.memory",
  sessions: "agents.tabs.sessions",
};

export function AgentDetailTabs({ agent, typeRow, rowActions }: Props) {
  const { t } = useTranslation();
  // The Model tab is about connections to model providers, so it exists only
  // while the Models feature is on; with it off the tab is simply not there and
  // its address falls back to Overview like any unknown tab.
  const models = useFeatureEnabled("models");
  const tabs = models === true ? AGENT_TABS : AGENT_TABS.filter((id) => id !== "model");
  const [tab, setTab] = useDetailTab(tabs, DEFAULT_AGENT_TAB, agentBasePath(agent.type), {
    enabled: models !== undefined,
  });
  const { open } = rowActions;
  const overviewActions = {
    onConnection: (kind: "connect" | "disconnect") => open.change(kind),
    onEnable: open.enable,
    onChangeConfigDir: open.configDir,
    onRemove: open.remove,
    busy: !!rowActions.pending,
  };

  return (
    <Tabs value={tab} onValueChange={setTab} className="flex min-h-0 flex-col">
      <TabsList className="overflow-x-auto">
        {tabs.map((id) => (
          <TabsTrigger key={id} value={id}>
            {t(LABEL_KEY[id])}
          </TabsTrigger>
        ))}
      </TabsList>
      <TabsContent value={tab} className="mt-[18px] min-h-0">
        {tab === "overview" && (
          <AgentOverviewTab agent={agent} typeRow={typeRow} actions={overviewActions} />
        )}
        {tab === "model" && <AgentModelTab agent={agent} />}
        {tab === "skills" && <AgentSkillsTab agent={agent} />}
        {tab === "mcp-servers" && <AgentMcpServersTab agent={agent} />}
        {tab === "plugins" && <AgentPluginsTab agent={agent} />}
        {tab === "hooks" && <AgentHooksTab agent={agent} onRepair={() => open.change("connect")} />}
        {tab === "config" && <AgentConfigFilesTab agent={agent} />}
        {tab === "memory" && <AgentMemoryTab agent={agent} />}
        {tab === "sessions" && <AgentSessionsTab agent={agent} />}
      </TabsContent>
    </Tabs>
  );
}
