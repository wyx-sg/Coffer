// frontend/src/components/mcp/McpServerDetailTabs.tsx — the tab strip and panes of the open MCP server.
//
// Overview · Tools · Resources · Prompts · Invocations, the tab in the path
// (`/mcp-servers/<name>/tools`; spec web-ui "Lay out every detail page's tabs
// alike"). No counts in the labels. The pane hands in every tab's content.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useDetailTab } from "@/lib/detailTabs";
import { MCP_SERVER_TABS } from "./mcpServerTabs";

interface Props {
  /** The page's bare address (`/mcp-servers/<name>`); a tab is a segment under it. */
  basePath: string;
  overview: ReactNode;
  tools: ReactNode;
  resources: ReactNode;
  prompts: ReactNode;
  invocations: ReactNode;
}

export function McpServerDetailTabs({
  basePath,
  overview,
  tools,
  resources,
  prompts,
  invocations,
}: Props) {
  const { t } = useTranslation();
  const [tab, setTab] = useDetailTab(MCP_SERVER_TABS, "overview", basePath);
  return (
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList>
        <TabsTrigger value="overview">{t("mcp.server.tabs.overview")}</TabsTrigger>
        <TabsTrigger value="tools">{t("mcp.server.tabs.tools")}</TabsTrigger>
        <TabsTrigger value="resources">{t("mcp.server.tabs.resources")}</TabsTrigger>
        <TabsTrigger value="prompts">{t("mcp.server.tabs.prompts")}</TabsTrigger>
        <TabsTrigger value="invocations">{t("mcp.server.tabs.invocations")}</TabsTrigger>
      </TabsList>

      <TabsContent value="overview" className="pt-5">
        {overview}
      </TabsContent>
      <TabsContent value="tools" className="pt-5">
        {tools}
      </TabsContent>
      <TabsContent value="resources" className="pt-5">
        {resources}
      </TabsContent>
      <TabsContent value="prompts" className="pt-5">
        {prompts}
      </TabsContent>
      <TabsContent value="invocations" className="pt-5">
        {invocations}
      </TabsContent>
    </Tabs>
  );
}
