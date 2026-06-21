// frontend/src/components/agents/AgentGatewayMcpSection.tsx — spec 004.
// Section A of the agent "MCP servers" tab: the servers Coffer exposes through
// the gateway are managed on the standalone MCP servers page, so this section
// does NOT re-list them — it renders the shared CofferGatewayCard, which shows a
// link to that page when Coffer MCP is installed on the agent, or the shared
// "Coffer MCP not installed" note otherwise (the gateway is the only way the
// agent reaches these servers). The install button lives in the page header.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { CofferGatewayCard } from "@/components/agents/AgentManagedLink";

export function AgentGatewayMcpSection({ agentName }: { agentName: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <CofferGatewayCard
      agentName={agentName}
      title={t("agents.workspace.mcp.gatewayTitle")}
      hint={t("agents.workspace.mcp.gatewayManagedHint")}
      buttonLabel={t("agents.workspace.mcp.openServersPage")}
      onOpen={() => navigate("/mcp-servers")}
      notInstalledHint={t("agents.mcpTab.notInstalled")}
    />
  );
}
