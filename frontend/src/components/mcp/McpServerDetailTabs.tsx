// frontend/src/components/mcp/McpServerDetailTabs.tsx — the tab strip and panes of the open MCP server.
//
// Overview · Tools · Resources · Prompts · Invocations, the tab in the path
// (`/mcp-servers/<name>/tools`; spec web-ui "Lay out every detail page's tabs
// alike"). The pane hands in what Overview and Tools show; Resources and
// Prompts are the shared capability table, Invocations the invocation log
// scoped to this server (spec web-ui "Scope Activity's calls table to one
// server on its page").
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { components } from "@/lib/api/types";
import { useDetailTab } from "@/lib/detailTabs";
import { CapabilityList } from "./CapabilityList";
import { InvocationsTable } from "./InvocationsTable";
import { MCP_SERVER_TABS } from "./mcpServerTabs";

type CapabilityListOut = components["schemas"]["CapabilityListOut"];

interface Props {
  serverUid: string;
  /** The page's bare address (`/mcp-servers/<name>`); a tab is a segment under it. */
  basePath: string;
  capabilities: CapabilityListOut | undefined;
  capsError?: unknown;
  overview: ReactNode;
  tools: ReactNode;
}

export function McpServerDetailTabs({
  serverUid,
  basePath,
  capabilities,
  capsError,
  overview,
  tools,
}: Props) {
  const { t } = useTranslation();
  const [tab, setTab] = useDetailTab(MCP_SERVER_TABS, "overview", basePath);
  const count = (n: number | undefined) =>
    n ? (
      <span className="text-text-muted" aria-hidden>
        · {n}
      </span>
    ) : null;

  return (
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList>
        <TabsTrigger value="overview">{t("mcp.server.tabs.overview")}</TabsTrigger>
        <TabsTrigger value="tools">
          {t("mcp.server.tabs.tools")}
          {count(capabilities?.tools?.length)}
        </TabsTrigger>
        <TabsTrigger value="resources">
          {t("mcp.server.tabs.resources")}
          {count(capabilities?.resources?.length)}
        </TabsTrigger>
        <TabsTrigger value="prompts">
          {t("mcp.server.tabs.prompts")}
          {count(capabilities?.prompts?.length)}
        </TabsTrigger>
        <TabsTrigger value="invocations">{t("mcp.server.tabs.invocations")}</TabsTrigger>
      </TabsList>

      <TabsContent value="overview" className="pt-5">
        {overview}
      </TabsContent>
      <TabsContent value="tools" className="pt-5">
        {tools}
      </TabsContent>
      <TabsContent value="resources" className="pt-5">
        <CapabilityList
          serverUid={serverUid}
          kind="resource"
          resources={capabilities?.resources}
          error={capsError}
          fromCache={capabilities?.from_cache}
        />
      </TabsContent>
      <TabsContent value="prompts" className="pt-5">
        <CapabilityList
          serverUid={serverUid}
          kind="prompt"
          prompts={capabilities?.prompts}
          error={capsError}
          fromCache={capabilities?.from_cache}
        />
      </TabsContent>
      <TabsContent value="invocations" className="pt-5">
        <InvocationsTable serverUid={serverUid} />
      </TabsContent>
    </Tabs>
  );
}
