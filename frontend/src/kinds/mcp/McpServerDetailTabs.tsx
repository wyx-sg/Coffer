// frontend/src/kinds/mcp/McpServerDetailTabs.tsx
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CapabilityList } from "./CapabilityList";
import { InvocationsTable } from "./InvocationsTable";
import { useMcpInvocations } from "@/lib/hooks/useMcpInvocations";
import { formatDateTime } from "@/lib/utils";
import type { components } from "@/lib/api/types";

type CapabilityListOut = components["schemas"]["CapabilityListOut"];

interface Props {
  serverName: string;
  capabilities: CapabilityListOut | undefined;
  capsError?: unknown;
  config: unknown;
  isCapsPending: boolean;
  onRefresh: () => void;
}

interface OverviewFields {
  transportType: string;
  command: string | null;
  url: string | null;
}

function extractOverview(config: unknown): OverviewFields {
  const transport = (config as Record<string, unknown> | null)?.transport;
  if (transport && typeof transport === "object") {
    const t = transport as Record<string, unknown>;
    const transportType = typeof t.type === "string" ? t.type : "unknown";
    const command = typeof t.command === "string" ? t.command : null;
    const args = Array.isArray(t.args) ? t.args.map(String).join(" ") : "";
    const url = typeof t.url === "string" ? t.url : null;
    return {
      transportType,
      command: command ? (args ? `${command} ${args}` : command) : null,
      url,
    };
  }
  return { transportType: "unknown", command: null, url: null };
}

export function McpServerDetailTabs({
  serverName,
  capabilities,
  capsError,
  config,
  isCapsPending,
  onRefresh,
}: Props) {
  const { t } = useTranslation();
  const overview = extractOverview(config);
  // Last invocation timestamp — limit=1 is the cheapest read. We don't
  // care about the loading state; while pending the row reads "—".
  const { data: invocations } = useMcpInvocations({ serverName, limit: 1 });
  const lastInvocationAt = invocations?.invocations?.[0]?.timestamp ?? null;

  return (
    <Tabs defaultValue="overview">
      <div className="flex flex-wrap items-center gap-3">
        <TabsList>
          <TabsTrigger value="overview">{t("mcp.server.tabs.overview")}</TabsTrigger>
          <TabsTrigger value="tools">{t("mcp.server.tabs.tools")}</TabsTrigger>
          <TabsTrigger value="resources">{t("mcp.server.tabs.resources")}</TabsTrigger>
          <TabsTrigger value="prompts">{t("mcp.server.tabs.prompts")}</TabsTrigger>
          <TabsTrigger value="invocations">{t("mcp.server.tabs.invocations")}</TabsTrigger>
        </TabsList>
        <Button
          size="sm"
          variant="outline"
          onClick={onRefresh}
          disabled={isCapsPending}
          aria-label={t("mcp.server.refresh")}
        >
          <RefreshCw className="mr-1 size-3" />
          {t("mcp.server.refresh")}
        </Button>
      </div>

      <TabsContent value="overview" className="pt-6">
        <Card className="paper-card">
          <CardHeader>
            <CardTitle className="font-serif text-lg">{t("mcp.server.overview.config")}</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-3 text-sm sm:grid-cols-[minmax(8rem,auto)_1fr]">
              <dt className="text-muted-foreground">{t("mcp.server.overview.transport")}</dt>
              <dd className="font-mono">{overview.transportType}</dd>

              {overview.transportType === "stdio" && overview.command ? (
                <>
                  <dt className="text-muted-foreground">{t("mcp.server.overview.command")}</dt>
                  <dd className="break-all font-mono text-xs">{overview.command}</dd>
                </>
              ) : null}

              {overview.transportType === "http" && overview.url ? (
                <>
                  <dt className="text-muted-foreground">{t("mcp.server.overview.url")}</dt>
                  <dd className="break-all font-mono text-xs">{overview.url}</dd>
                </>
              ) : null}

              <dt className="text-muted-foreground">{t("mcp.server.overview.tools")}</dt>
              <dd>{capsError ? "—" : (capabilities?.tools?.length ?? 0)}</dd>

              <dt className="text-muted-foreground">{t("mcp.server.overview.resources")}</dt>
              <dd>{capsError ? "—" : (capabilities?.resources?.length ?? 0)}</dd>

              <dt className="text-muted-foreground">{t("mcp.server.overview.prompts")}</dt>
              <dd>{capsError ? "—" : (capabilities?.prompts?.length ?? 0)}</dd>

              <dt className="text-muted-foreground">{t("mcp.server.overview.lastInvocation")}</dt>
              <dd>{lastInvocationAt ? formatDateTime(lastInvocationAt) : "—"}</dd>
            </dl>

            <details className="mt-4">
              <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
                {t("mcp.server.overview.rawConfig")}
              </summary>
              <pre className="mt-2 overflow-x-auto rounded-md bg-secondary/50 p-4 font-mono text-xs leading-relaxed text-foreground/80">
                {JSON.stringify(config, null, 2)}
              </pre>
            </details>
          </CardContent>
        </Card>
      </TabsContent>

      <TabsContent value="tools" className="pt-6">
        <CapabilityList
          serverName={serverName}
          kind="tool"
          tools={capabilities?.tools}
          error={capsError}
        />
      </TabsContent>
      <TabsContent value="resources" className="pt-6">
        <CapabilityList
          serverName={serverName}
          kind="resource"
          resources={capabilities?.resources}
          error={capsError}
        />
      </TabsContent>
      <TabsContent value="prompts" className="pt-6">
        <CapabilityList
          serverName={serverName}
          kind="prompt"
          prompts={capabilities?.prompts}
          error={capsError}
        />
      </TabsContent>
      <TabsContent value="invocations" className="pt-6">
        <InvocationsTable serverName={serverName} />
      </TabsContent>
    </Tabs>
  );
}
