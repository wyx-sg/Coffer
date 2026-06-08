// frontend/src/kinds/mcp/McpServerDetailPage.tsx
import { useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useResource } from "@/lib/hooks/useResources";
import {
  useDeleteResource,
  useEnableResource,
  useDisableResource,
} from "@/lib/hooks/useResourceMutations";
import { useMcpCapabilities } from "@/lib/hooks/useMcpCapabilities";
import { useMcpServerStatus } from "@/lib/hooks/useMcpInvocations";
import { getApiClient } from "@/lib/api/client";
import { type HealthState } from "./HealthBadge";
import { McpServerDetailHeader } from "./McpServerDetailHeader";
import { McpServerDetailTabs } from "./McpServerDetailTabs";
import { McpServerDeleteDialog } from "./McpServerDeleteDialog";

interface TestResult {
  ok: boolean;
  latency_ms: number;
  protocol_version?: string | null;
  error_message?: string | null;
}

export function McpServerDetailPage() {
  const { t } = useTranslation();
  const { name = "" } = useParams<{ name: string }>();
  const navigate = useNavigate();
  // When navigated here from an agent's MCP servers tab, location.state carries
  // a return target so we can offer a "back to <agent>" button.
  const backState = useLocation().state as { backTo?: string; backLabel?: string } | null;
  const qc = useQueryClient();
  const { data: resource, isPending, error } = useResource("mcp_server", name);
  const {
    isPending: capsPending,
    data: capabilities,
    error: capsError,
  } = useMcpCapabilities(name, !isPending && !error);
  const { data: serverStatus } = useMcpServerStatus(name);
  const enable = useEnableResource();
  const disable = useDisableResource();
  const del = useDeleteResource();
  const [deleteOpen, setDeleteOpen] = useState(false);

  const runTest = useMutation({
    mutationFn: async (): Promise<TestResult> => {
      const client = getApiClient();
      const { data, error: e } = await client.POST("/resources/mcp_server/{name}/test", {
        params: { path: { name } },
      });
      if (e) throw new Error(e.error?.message ?? "test failed");
      return data as TestResult;
    },
  });

  // Derive the test outcome straight from the mutation rather than mirroring
  // it into separate state: a transport failure becomes a failing result.
  const testResult: TestResult | null =
    runTest.data ??
    (runTest.error ? { ok: false, latency_ms: 0, error_message: runTest.error.message } : null);

  // Prefer an explicit test result; else use the persisted /status endpoint
  // (same source as the list card) so both views agree without waiting for
  // the slow live /capabilities discovery.
  const healthState: HealthState = (() => {
    if (testResult !== null) return testResult.ok ? "healthy" : "failing";
    return serverStatus ?? "unknown";
  })();

  const handleDelete = () => {
    del.mutate(
      { kind: "mcp_server", name },
      {
        onSuccess: () => {
          void qc.invalidateQueries({ queryKey: ["resources"] });
          navigate("/mcp-servers");
        },
      },
    );
  };

  if (isPending) {
    return (
      <Card className="paper-card">
        <CardContent className="py-12 text-center text-muted-foreground">
          {t("common.loading")}
        </CardContent>
      </Card>
    );
  }
  if (error || !resource) {
    return (
      <Card className="paper-card border-destructive/40">
        <CardHeader>
          <CardTitle className="font-serif text-destructive">
            {t("errors.RESOURCE_NOT_FOUND")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-foreground/80">
            {error instanceof Error ? error.message : t("errors.RESOURCE_NOT_FOUND")}
          </p>
          <Button variant="link" onClick={() => navigate("/mcp-servers")}>
            <ArrowLeft className="mr-1 size-4" />
            {t("mcp.server.backToResources")}
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="-ml-2 flex flex-wrap items-center gap-1">
        {backState?.backTo ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate(backState.backTo!)}
            className="text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="mr-1.5 size-4" />
            {t("common.backTo", { label: backState.backLabel ?? "" })}
          </Button>
        ) : null}
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate("/mcp-servers")}
          className="text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="mr-1.5 size-4" /> {t("mcp.server.backToResources")}
        </Button>
      </div>

      <McpServerDetailHeader
        resource={resource}
        healthState={healthState}
        testResult={testResult}
        isTestPending={runTest.isPending}
        isEnablePending={enable.isPending}
        isDisablePending={disable.isPending}
        onTestConnection={() => runTest.mutate()}
        onToggleEnabled={(checked) => {
          const m = checked ? enable : disable;
          m.mutate({ kind: "mcp_server", name });
        }}
        onDeleteClick={() => setDeleteOpen(true)}
      />

      {testResult && !testResult.ok ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 px-4 py-2.5 text-sm text-destructive">
          {t("mcp.server.testFailure", {
            latency: testResult.latency_ms,
            error: testResult.error_message,
          })}
        </div>
      ) : null}

      <McpServerDetailTabs
        serverName={name}
        capabilities={capabilities}
        capsError={capsError}
        config={resource.config}
        isCapsPending={capsPending}
        onRefresh={() => {
          void qc.invalidateQueries({
            queryKey: ["mcp", "capabilities", name],
          });
        }}
      />

      <McpServerDeleteDialog
        name={name}
        open={deleteOpen}
        isPending={del.isPending}
        onOpenChange={setDeleteOpen}
        onConfirm={handleDelete}
      />
    </div>
  );
}
