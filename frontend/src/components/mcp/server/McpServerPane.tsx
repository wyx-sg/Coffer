// src/components/mcp/server/McpServerPane.tsx — the open MCP server in the MCP servers page's reading pane (design 4.1.04–4.1.19).
//
// The header with the state pill and its fixed actions, then the path tabs;
// the Overview opens with the banner that answers "why, and what next" and
// carries the fix. It owns the pane's dialogs, the Server log drawer and the
// toasts (test passed, turned off with Undo, config copied); the page owns the
// address. Everything it reads is persisted state (status, 24 h summary,
// tiering) except the capability list: live while the server is healthy or not
// checked yet, the saved switches while it is failing, off or missing
// something — so a server that doesn't answer never holds the page on the
// discovery timeout.
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { EditMcpServerDialog } from "@/components/mcp/EditMcpServerDialog";
import { McpServerDetailTabs } from "@/components/mcp/McpServerDetailTabs";
import { ReplaceSecretDialog } from "@/components/secret/ReplaceSecretDialog";
import { useToast } from "@/components/ui/toast";
import {
  mcpCapabilitiesKey,
  mcpStatusKey,
  mcpSummaryKey,
  mcpTieringKey,
  resourcesKey,
} from "@/lib/api/queryKeys";
import type { ResourceOut } from "@/lib/api/resources";
import { useAgents } from "@/lib/hooks/useAgents";
import { useMcpCapabilities } from "@/lib/hooks/useMcpCapabilities";
import { useMcpInvocationSummary, useMcpToolTiering } from "@/lib/hooks/useMcpServerPage";
import { useTestMcpServer } from "@/lib/hooks/useMcpServerMutations";
import { useMcpServerStatusDetail } from "@/lib/hooks/useMcpServerStatus";
import { useDisableResource, useEnableResource } from "@/lib/hooks/useResourceMutations";
import { useSecrets } from "@/lib/hooks/useSecrets";
import { rebindMcpSecret } from "@/lib/mcp/rebindMcpSecret";
import { secretsKey } from "@/lib/api/queryKeys";
import { McpCapabilityTab } from "./McpCapabilityTab";
import { McpDeleteDialog } from "./McpDeleteDialog";
import { McpLogDrawer } from "./McpLogDrawer";
import { McpOverviewTab } from "./McpOverviewTab";
import { McpServerHeader } from "./McpServerHeader";
import { McpStatusCallout } from "./McpStatusCallout";
import { McpToolsTab } from "./McpToolsTab";
import { McpTopTools } from "./McpTopTools";
import { reachedAgents } from "./reachWords";
import { joinNames, serverState, transportOf } from "@/lib/mcp/serverState";
import { failedTest, type TestResult } from "./testResult";

interface Props {
  resource: ResourceOut;
  basePath: string;
  onDeleted: () => void;
}

export function McpServerPane({ resource, basePath, onDeleted }: Props) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const uid = resource.uid;
  const { data: agents = [] } = useAgents();
  const detailRead = useMcpServerStatusDetail(uid);
  const detail = detailRead.data;
  const state = serverState(resource, detail);
  const transport = transportOf(resource.config);
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
  const secrets = useSecrets(state.kind === "secretMissing");
  const [edit, setEdit] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const [addingSecret, setAddingSecret] = useState(false);

  const toolCount = caps.data?.tools?.length || tiering?.tool_count || 0;
  const agentNames = joinNames(
    reachedAgents(resource, agents).map((a) => a.display_name),
    i18n.language,
  );
  // Only a failed test speaks in the Overview; a pass is a toast.
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
  const runTestNow = () =>
    runTest.mutate(undefined, {
      onSuccess: (result) => {
        if (result.ok)
          toast.success(t("mcp.page.testPassedToast", { count: result.tool_count ?? 0 }), {
            description: t("mcp.page.testPassedBody"),
          });
      },
      onSettled: refresh,
    });
  // Replace key… on a Requires row: the same config, that one env var / header citing another secret.
  const rebindSecret = async (field: string, ref: string) => {
    await rebindMcpSecret(resource, field, ref);
    void qc.invalidateQueries({ queryKey: resourcesKey });
    void qc.invalidateQueries({ queryKey: secretsKey });
    refresh();
  };
  const turnOn = () => enable.mutate({ kind: "mcp_server", uid });
  const turnOff = () =>
    disable.mutate(
      { kind: "mcp_server", uid },
      {
        onSuccess: () =>
          toast.success(t("mcp.page.turnedOff", { name: resource.name }), {
            description: t("mcp.page.turnedOffBody"),
            undo: turnOn,
          }),
      },
    );
  const copyConfig = async () => {
    // The config carries secret refs only, never a secret value.
    try {
      await navigator.clipboard.writeText(
        JSON.stringify({ [resource.name]: resource.config }, null, 2),
      );
      toast.success(t("mcp.page.configCopied"), {
        description: t("mcp.page.configCopiedBody", { name: resource.name }),
      });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  };
  // The Activity page on this server's calls (its search matches the server name).
  const activityHref = `/activity?tab=mcp&q=${encodeURIComponent(resource.name)}`;
  // "View errors" (a server Coffer does not start has no log): Activity on its failed calls.
  const viewErrors = () => navigate(`${activityHref}&status=failed`);
  const missingRow = secrets.data?.refs.find((r) => r.ref === detail?.missing_secret_ref) ?? null;
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
        onTest={runTestNow}
        onEdit={() => setEdit(true)}
        onOpenLog={() => setLogOpen(true)}
        onCopyConfig={() => void copyConfig()}
        onTurnOff={turnOff}
        onDelete={() => setDeleting(true)}
      />
      <McpServerDetailTabs
        basePath={basePath}
        overview={
          <McpOverviewTab
            activityHref={activityHref}
            name={resource.name}
            enabled={resource.enabled}
            state={state}
            agents={agents}
            summary={summary.data}
            summaryPending={summary.isPending}
            requires={detail?.requires}
            onRebindSecret={rebindSecret}
            callout={
              <McpStatusCallout
                name={resource.name}
                state={state}
                detail={detail}
                isHttp={transport.type === "http"}
                toolCount={toolCount}
                agentNames={agentNames}
                test={test}
                onOpenLog={() => setLogOpen(true)}
                onViewErrors={viewErrors}
                onTurnOn={turnOn}
                onAddSecret={() => setAddingSecret(true)}
                onReplaceKey={() => setEdit(true)}
              />
            }
            tools={
              <McpTopTools
                {...capsProps}
                name={resource.name}
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
      />

      {edit ? (
        <EditMcpServerDialog
          resource={resource}
          open
          onOpenChange={(open) => (open ? undefined : setEdit(false))}
        />
      ) : null}
      <ReplaceSecretDialog
        row={addingSecret ? missingRow : null}
        onOpenChange={(open) => {
          if (open) return;
          setAddingSecret(false);
          refresh();
        }}
      />
      <McpDeleteDialog
        resource={resource}
        open={deleting}
        onOpenChange={setDeleting}
        agentNames={agentNames}
        toolCount={toolCount}
        onDeleted={onDeleted}
      />
      <McpLogDrawer resource={resource} open={logOpen} onClose={() => setLogOpen(false)} />
    </div>
  );
}
