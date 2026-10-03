// src/components/agents/detail/AgentDetailTabs.tsx — the agent page's tabs, each at its own path.
//
// Overview · Skills · MCP servers · Hooks · Config files · Sessions, then More
// (Plugins · Memory, the least used) — no counts. The open tab is the path
// segment (`useDetailTab`); only the open tab is mounted, so a tab reads its
// data when it is opened. A tab inside More that needs attention (a plugin
// whose files are gone, Coffer's memory hook out of order) puts a dot on More,
// and while one of them is open More wears its name and the underline. There is
// no Model tab: the model is a section of Overview. Leaving Config files with
// an unsaved draft asks first, through the shell's unsaved-changes guard, like
// every other way out of an editor.
import { useTranslation } from "react-i18next";

import { AgentConfigFilesTab } from "@/components/agents/AgentConfigFilesTab";
import { AgentHooksTab } from "@/components/agents/AgentHooksTab";
import { AgentPluginsTab } from "@/components/agents/AgentPluginsTab";
import { AgentMcpServersTab } from "@/components/agents/AgentMcpServersTab";
import { AgentMemoryTab } from "@/components/agents/AgentMemoryTab";
import { AgentOverviewTab } from "@/components/agents/AgentOverviewTab";
import { AgentSkillsTab } from "@/components/agents/AgentSkillsTab";
import type { useAgentRowActions } from "@/components/agents/list/useAgentRowActions";
import { AgentSessionsTab } from "@/components/agents/sessions/AgentSessionsTab";
import { DetailTabsMore, type DetailTab } from "@/components/DetailTabsMore";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import {
  AGENT_MORE_TABS,
  AGENT_PRIMARY_TABS,
  AGENT_TABS,
  agentBasePath,
  DEFAULT_AGENT_TAB,
  type AgentTab,
} from "@/lib/agents/routes";
import type { AgentOut, AgentTypeOut } from "@/lib/api/agents";
import { useDetailTab } from "@/lib/detailTabs";
import { useAgentHooks, useAgentPlugins } from "@/lib/hooks/useAgents";
import { useFeatureEnabled } from "@/lib/hooks/useFeatures";

interface Props {
  agent: AgentOut;
  typeRow: AgentTypeOut;
  rowActions: ReturnType<typeof useAgentRowActions>;
}

const LABEL_KEY: Record<AgentTab, string> = {
  overview: "agents.tabs.overview",
  skills: "agents.tabs.skills",
  "mcp-servers": "agents.tabs.mcpServers",
  plugins: "agents.tabs.plugins",
  hooks: "agents.tabs.hooks",
  config: "agents.tabs.config",
  memory: "agents.tabs.memory",
  sessions: "agents.tabs.sessions",
};

/** Which of the tabs behind More hold something that needs the user. */
function useMoreAttention(uid: string): Partial<Record<AgentTab, boolean>> {
  const plugins = useAgentPlugins(uid).data?.items;
  const hook = useAgentHooks(uid).data?.coffer_hook;
  const memoryOn = useFeatureEnabled("memory") === true;
  return {
    plugins: !!plugins?.some((p) => p.cache_present === false),
    // The memory tab carries Coffer's memory hook, and Repair when it is off.
    memory: memoryOn && !!hook && hook.health !== "current",
  };
}

export function AgentDetailTabs({ agent, typeRow, rowActions }: Props) {
  const { t } = useTranslation();
  const [tab, setTab] = useDetailTab(AGENT_TABS, DEFAULT_AGENT_TAB, agentBasePath(agent.type));
  const attention = useMoreAttention(agent.uid);
  const entry = (id: AgentTab): DetailTab => ({
    id,
    label: t(LABEL_KEY[id]),
    attention: attention[id],
  });
  const { open } = rowActions;
  const overviewActions = {
    onConnection: (kind: "connect" | "disconnect") => open.change(kind),
    onEnable: open.enable,
    onChangeConfigDir: open.configDir,
    busy: !!rowActions.pending,
  };

  return (
    <Tabs value={tab} onValueChange={setTab} className="flex min-h-0 flex-col">
      <DetailTabsMore
        tabs={AGENT_PRIMARY_TABS.map(entry)}
        more={AGENT_MORE_TABS.map(entry)}
        value={tab}
        onSelect={setTab}
        moreLabel={t("agents.tabs.more")}
        className="overflow-x-auto"
      />
      <TabsContent value={tab} className="mt-[18px] min-h-0">
        {tab === "overview" && (
          <AgentOverviewTab agent={agent} typeRow={typeRow} actions={overviewActions} />
        )}
        {tab === "skills" && <AgentSkillsTab agent={agent} />}
        {tab === "mcp-servers" && <AgentMcpServersTab agent={agent} />}
        {tab === "plugins" && <AgentPluginsTab agent={agent} />}
        {tab === "hooks" && <AgentHooksTab agent={agent} onRepair={() => open.change("connect")} />}
        {tab === "config" && <AgentConfigFilesTab agent={agent} />}
        {tab === "memory" && (
          <AgentMemoryTab agent={agent} onRepair={() => open.change("connect")} />
        )}
        {tab === "sessions" && <AgentSessionsTab agent={agent} />}
      </TabsContent>
    </Tabs>
  );
}
