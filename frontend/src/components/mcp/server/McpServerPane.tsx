// src/components/mcp/server/McpServerPane.tsx — the open MCP server in the MCP servers page's reading pane (design 4.1.02–4.1.12, 4.1.25–4.1.28).
//
// The header with the state pill and actions, then the path tabs; the
// Overview opens with the callout that answers "why, and what next". It owns
// the pane's dialogs and the log drawer; the page owns the address.
// Everything it reads is persisted state (status, 24 h summary, tiering) except
// the capability list: live while the server is healthy or not checked yet,
// the saved switches while it is failing, off or missing something — so a
// server that doesn't answer never holds the page on the discovery timeout.
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
import { useAgents } from "@/lib/hooks/useAgents";
import { useMcpCapabilities } from "@/lib/hooks/useMcpCapabilities";
import { useMcpInvocationSummary, useMcpToolTiering } from "@/lib/hooks/useMcpServerPage";
import { useTestMcpServer } from "@/lib/hooks/useMcpServerMutations";
import { useMcpServerStatusDetail } from "@/lib/hooks/useMcpServerStatus";
import { useDisableResource, useEnableResource } from "@/lib/hooks/useResourceMutations";
import { McpCallsLog } from "./McpCallsLog";
import { McpCapabilityTab } from "./McpCapabilityTab";
import { McpDeleteDialog } from "./McpDeleteDialog";
import { McpLogDrawer, type LogTab } from "./McpLogDrawer";
import { McpOverviewTab } from "./McpOverviewTab";
import { McpSecretFacts } from "./McpSecretFacts";
import { McpServerHeader } from "./McpServerHeader";
import { McpStatusCallout } from "./McpStatusCallout";
import { McpToolsTab } from "./McpToolsTab";
import { McpTopTools } from "./McpTopTools";
import { reachedAgents } from "./reachWords";
import { joinNames, serverState } from "@/lib/mcp/serverState";
import { failedTest, type TestResult } from "./testResult";

interface Props {
  resource: ResourceOut;
  basePath: string;
  onDeleted: () => void;
}

export function McpServerPane({ resource, basePath, onDeleted }: Props) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const qc = useQueryClient();
  const uid = resource.uid;
  const { data: agents = [] } = useAgents();
  const detailRead = useMcpServerStatusDetail(uid);
  const detail = detailRead.data;
  const state = serverState(resource, detail);
  const live = !detailRead.isPending && (state.kind === "healthy" || state.kind === "unknown");
  const liveCaps = useMcpCapabilities(uid, { enabled: live });
  const savedCaps = useMcpCapabilities(uid, {
    enabled: !detailRead.isPending && !live,
    saved: true,
  });
  const caps = live ? liveCaps : savedCaps;
  const capsPending = detailRead.isPending || caps.isPending;
  const summary = useMcpInvocationSummary(uid);
  const { data: tiering } = useMcpToolTiering(uid);
  const runTest = useTestMcpServer(uid);
  const enable = useEnableResource();
  const disable = useDisableResource();
  const [edit, setEdit] = useState<{ focus?: "secret" } | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [logTab, setLogTab] = useState<LogTab | null>(null);

  const toolCount = caps.data?.tools?.length || tiering?.tool_count || 0;
  const agentNames = joinNames(
    reachedAgents(resource, agents).map((a) => a.display_name),
    i18n.language,
  );
  const test: TestResult | null =
    (runTest.data as TestResult | undefined) ??
    (runTest.error ? failedTest(runTest.error.message) : null);

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
  const capsProps = {
    serverUid: uid,
    capabilities: caps.data,
    pending: capsPending,
    error: caps.error,
    summary: summary.data,
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
      <McpServerDetailTabs
        basePath={basePath}
        counts={{
          tools: toolCount,
          resources: caps.data?.resources?.length,
          prompts: caps.data?.prompts?.length,
        }}
        overview={
          <McpOverviewTab
            enabled={resource.enabled}
            state={state}
            agents={agents}
            tiering={tiering}
            summary={summary.data}
            summaryPending={summary.isPending}
            callout={
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
            }
            facts={
              state.kind === "secretMissing" ? (
                <McpSecretFacts resource={resource} detail={detail} />
              ) : null
            }
            tools={
              <McpTopTools
                {...capsProps}
                state={state}
                detail={detail}
                tiering={tiering}
                toolsHref={`${basePath}/tools`}
              />
            }
          />
        }
        tools={<McpToolsTab {...capsProps} state={state} detail={detail} tiering={tiering} />}
        resources={<McpCapabilityTab {...capsProps} kind="resource" />}
        prompts={<McpCapabilityTab {...capsProps} kind="prompt" />}
        invocations={<McpCallsLog serverUid={uid} agents={agents} />}
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
