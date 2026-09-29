// src/components/agents/detail/AgentDetailTabs.tsx — the agent page's nine tabs, each at its own path.
//
// Overview · Model · Skills · MCP servers · Plugins · Hooks · Config files ·
// Memory · Sessions (spec agent-registry, "the agent detail page carries nine
// tabs"). The open tab is the path segment (`useDetailTab`); only the open
// tab is mounted, so a tab reads its data when it is opened. The list tabs
// carry their count, read from the same queries the tabs make. Leaving Config
// files with an unsaved draft asks first.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { AgentConfigFilesTab } from "@/components/agents/AgentConfigFilesTab";
import { AgentHooksTab } from "@/components/agents/AgentHooksTab";
import { AgentMcpServersTab } from "@/components/agents/AgentMcpServersTab";
import { AgentMemoryTab } from "@/components/agents/AgentMemoryTab";
import { AgentOverviewTab } from "@/components/agents/AgentOverviewTab";
import { AgentPluginsTab } from "@/components/agents/AgentPluginsTab";
import { AgentSkillsTab } from "@/components/agents/AgentSkillsTab";
import type { useAgentRowActions } from "@/components/agents/list/useAgentRowActions";
import { AgentModelTab } from "@/components/agents/model/AgentModelTab";
import { AgentSessionsTab } from "@/components/agents/sessions/AgentSessionsTab";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AGENT_TABS, agentBasePath, DEFAULT_AGENT_TAB, type AgentTab } from "@/lib/agents/routes";
import type { AgentOut, AgentTypeOut } from "@/lib/api/agents";
import { useDetailTab } from "@/lib/detailTabs";
import { useAgentCounts } from "@/lib/hooks/useAgentCounts";

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

function sum(split: { coffer: number; own: number } | undefined): number | undefined {
  return split ? split.coffer + split.own : undefined;
}

export function AgentDetailTabs({ agent, typeRow, rowActions }: Props) {
  const { t } = useTranslation();
  const [tab, setTab] = useDetailTab(AGENT_TABS, DEFAULT_AGENT_TAB, agentBasePath(agent.type));
  const counts = useAgentCounts(agent.uid);
  const [configDirty, setConfigDirty] = useState(false);
  const [pendingTab, setPendingTab] = useState<string | null>(null);

  const count: Partial<Record<AgentTab, number | undefined>> = {
    skills: sum(counts.skills),
    "mcp-servers": sum(counts.mcp),
    plugins: counts.plugins?.total,
    hooks: counts.hooks?.total,
    sessions: counts.sessions,
  };

  const requestTab = (next: string) => {
    if (next === tab) return;
    if (configDirty && tab === "config") setPendingTab(next);
    else setTab(next);
  };

  const { open } = rowActions;
  const overviewActions = {
    onConnection: (kind: "connect" | "disconnect") => open.change(kind),
    onEnable: open.enable,
    onChangeConfigDir: open.configDir,
    onRemove: open.remove,
  };

  return (
    <Tabs value={tab} onValueChange={requestTab} className="flex min-h-0 flex-col">
      <TabsList className="overflow-x-auto">
        {AGENT_TABS.map((id) => (
          <TabsTrigger key={id} value={id}>
            {t(LABEL_KEY[id])}
            {count[id] ? (
              <span className="text-2xs font-book text-text-subtle">{count[id]}</span>
            ) : null}
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
        {tab === "config" && (
          <AgentConfigFilesTab agent={agent} onDirtyChange={setConfigDirty} />
        )}
        {tab === "memory" && <AgentMemoryTab agent={agent} />}
        {tab === "sessions" && <AgentSessionsTab agent={agent} />}
      </TabsContent>

      <ConfirmDialog
        open={pendingTab !== null}
        onOpenChange={(o) => !o && setPendingTab(null)}
        title={t("common.discardChanges.title")}
        description={t("common.discardChanges.body")}
        confirmLabel={t("common.discardChanges.confirm")}
        onConfirm={() => {
          if (pendingTab) setTab(pendingTab);
          setPendingTab(null);
          setConfigDirty(false);
        }}
      />
    </Tabs>
  );
}
