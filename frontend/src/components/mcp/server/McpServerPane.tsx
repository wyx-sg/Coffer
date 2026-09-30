// src/components/mcp/server/McpServerPane.tsx — the open MCP server in the MCP servers page's reading pane (design 4.1.02–4.1.12).
//
// The header with the state pill and actions, the callout that answers "why,
// and what next", then the path tabs. It owns the pane's dialogs and the log
// drawer; the page owns the address. Everything it reads is persisted state
// (status, 24 h summary, tiering) except the capability list, which is what
// the old detail page read too.
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { EditMcpServerDialog } from "@/components/mcp/EditMcpServerDialog";
import { McpServerDetailTabs } from "@/components/mcp/McpServerDetailTabs";
import { useToast } from "@/components/ui/toast";
import {
  mcpCapabilitiesKey,
  mcpStatusKey,
  mcpSummaryKey,
  mcpTieringKey,
} from "@/lib/api/queryKeys";
import type { ResourceOut } from "@/lib/api/resources";
import type { components } from "@/lib/api/types";
import { useAgents } from "@/lib/hooks/useAgents";
import { useMcpCapabilities } from "@/lib/hooks/useMcpCapabilities";
import { useMcpInvocationSummary, useMcpToolTiering } from "@/lib/hooks/useMcpServerPage";
import { useTestMcpServer } from "@/lib/hooks/useMcpServerMutations";
import { useMcpServerStatusDetail } from "@/lib/hooks/useMcpServerStatus";
import { useDisableResource, useEnableResource } from "@/lib/hooks/useResourceMutations";
import { McpDeleteDialog } from "./McpDeleteDialog";
import { McpLogDrawer, type LogTab } from "./McpLogDrawer";
import { McpOverviewTab } from "./McpOverviewTab";
import { McpServerHeader } from "./McpServerHeader";
import { McpStatusCallout } from "./McpStatusCallout";
import { McpToolsTab } from "./McpToolsTab";
import { McpTopTools } from "./McpTopTools";
import { reachedAgents } from "./reachWords";
import { serverState } from "./serverState";

type TestResult = components["schemas"]["McpTestResultOut"];

interface Props {
  resource: ResourceOut;
  basePath: string;
  onDeleted: () => void;
}

export function McpServerPane({ resource, basePath, onDeleted }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const qc = useQueryClient();
  const uid = resource.uid;
  const { data: agents = [] } = useAgents();
  const { data: detail } = useMcpServerStatusDetail(uid);
  const caps = useMcpCapabilities(uid);
  const summary = useMcpInvocationSummary(uid);
  const { data: tiering } = useMcpToolTiering(uid);
  const runTest = useTestMcpServer(uid);
  const enable = useEnableResource();
  const disable = useDisableResource();
  const [edit, setEdit] = useState<{ focus?: "secret" } | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [logTab, setLogTab] = useState<LogTab | null>(null);

  const state = serverState(resource, detail);
  const toolCount = caps.data?.tools?.length ?? tiering?.tool_count ?? 0;
  const agentNames = reachedAgents(resource, agents)
    .map((a) => a.display_name)
    .join(t("mcp.page.and"));
  const test: TestResult | null =
    runTest.data ??
    (runTest.error
      ? {
          ok: false,
          latency_ms: 0,
          error_message: runTest.error.message,
          protocol_version: null,
          server_capabilities: null,
        }
      : null);

  const refresh = () => {
    for (const key of [
      mcpStatusKey(uid),
      mcpCapabilitiesKey(uid),
      mcpTieringKey(uid),
      mcpSummaryKey(uid),
    ])
      void qc.invalidateQueries({ queryKey: key });
  };
  const copyConfig = async () => {
    // The config carries secret refs only, never a secret value.
    try {
      await navigator.clipboard.writeText(
        JSON.stringify({ [resource.name]: resource.config }, null, 2),
      );
      toast.success(t("mcp.page.configCopied"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="flex min-w-0 flex-col gap-4" data-testid="mcp-server-pane">
      <McpServerHeader
        resource={resource}
        state={state}
        testing={runTest.isPending}
        onTest={() => runTest.mutate(undefined, { onSettled: refresh })}
        onEdit={(focus) => setEdit({ focus })}
        onOpenLog={() => setLogTab("calls")}
        onCopyConfig={() => void copyConfig()}
        onTurn={(on) => (on ? enable : disable).mutate({ kind: "mcp_server", uid })}
        onDelete={() => setDeleting(true)}
      />
      <McpStatusCallout
        state={state}
        detail={detail}
        tiering={tiering}
        toolCount={toolCount}
        agentNames={agentNames}
        test={test}
        onOpenLog={() => setLogTab(state.kind === "launcherMissing" ? "log" : "calls")}
        onReplaceSecret={() => setEdit({ focus: "secret" })}
      />
      <McpServerDetailTabs
        serverUid={uid}
        basePath={basePath}
        capabilities={caps.data}
        capsError={caps.error}
        overview={
          <McpOverviewTab
            resource={resource}
            agents={agents}
            tiering={tiering}
            summary={summary.data}
            summaryPending={summary.isPending}
            tools={
              <McpTopTools
                serverUid={uid}
                capabilities={caps.data}
                pending={caps.isPending}
                error={caps.error}
                summary={summary.data}
                tiering={tiering}
                toolsHref={`${basePath}/tools`}
              />
            }
          />
        }
        tools={
          <McpToolsTab
            serverUid={uid}
            capabilities={caps.data}
            error={caps.error}
            summary={summary.data}
            tiering={tiering}
          />
        }
      />

      {edit ? (
        <EditMcpServerDialog
          resource={resource}
          open
          focus={edit.focus}
          onOpenChange={(open) => (open ? undefined : setEdit(null))}
        />
      ) : null}
      <McpDeleteDialog
        resource={resource}
        open={deleting}
        onOpenChange={setDeleting}
        agentNames={agentNames}
        toolCount={toolCount}
        onDeleted={onDeleted}
      />
      <McpLogDrawer
        resource={resource}
        agents={agents}
        summary={summary.data}
        tab={logTab}
        onTabChange={setLogTab}
        onClose={() => setLogTab(null)}
      />
    </div>
  );
}
