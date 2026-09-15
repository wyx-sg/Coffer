// frontend/src/pages/McpServerDetailPage.tsx
import { useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Server } from "lucide-react";
import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import { useResource } from "@/lib/hooks/useResources";
import { useDeleteResource } from "@/lib/hooks/useResourceMutations";
import { useMcpCapabilities } from "@/lib/hooks/useMcpCapabilities";
import { useMcpServerStatus } from "@/lib/hooks/useMcpServerStatus";
import { useTestMcpServer } from "@/lib/hooks/useMcpServerMutations";
import { mcpCapabilitiesKey } from "@/lib/api/queryKeys";
import type { components } from "@/lib/api/types";
import { type HealthState } from "@/components/mcp/HealthBadge";
import { McpServerDetailHeader } from "@/components/mcp/McpServerDetailHeader";
import { McpServerDetailTabs } from "@/components/mcp/McpServerDetailTabs";
import { McpServerDeleteDialog } from "@/components/mcp/McpServerDeleteDialog";

type TestResult = components["schemas"]["McpTestResultOut"];

export function McpServerDetailPage() {
  const { t } = useTranslation();
  const { name = "" } = useParams<{ name: string }>();
  const navigate = useNavigate();
  // When navigated here from an agent's MCP servers tab, location.state carries
  // a return target, so "← back" leads to that agent rather than the list.
  const backState = useLocation().state as { backTo?: string; backLabel?: string } | null;
  const back = backState?.backTo
    ? { to: backState.backTo, label: t("common.backTo", { label: backState.backLabel ?? "" }) }
    : { to: "/mcp-servers", label: t("mcp.server.backToResources") };
  const qc = useQueryClient();
  const { data: resource, isPending, error } = useResource("mcp_server", name);
  const {
    isPending: capsPending,
    data: capabilities,
    error: capsError,
  } = useMcpCapabilities(name, !isPending && !error);
  const { data: serverStatus } = useMcpServerStatus(name);
  const del = useDeleteResource();
  const [deleteOpen, setDeleteOpen] = useState(false);

  const runTest = useTestMcpServer(name);

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

  // useDeleteResource already refreshes the resources cache; the page only
  // has to leave once the server is gone.
  const handleDelete = () => {
    del.mutate({ kind: "mcp_server", name }, { onSuccess: () => navigate("/mcp-servers") });
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
    // The translated error is the title when it says more than "not found";
    // a plain not-found is not repeated as its own description.
    const title = t("errors.RESOURCE_NOT_FOUND");
    const message = error ? translateApiError(t, error) : null;
    return (
      <EmptyState
        icon={Server}
        title={title}
        description={message && message !== title ? message : undefined}
        action={
          <Button variant="outline" asChild>
            <Link to="/mcp-servers">
              <ArrowLeft className="mr-1 size-4" />
              {t("mcp.server.backToResources")}
            </Link>
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      <McpServerDetailHeader
        resource={resource}
        back={back}
        healthState={healthState}
        testResult={testResult}
        isTestPending={runTest.isPending}
        onTestConnection={() => runTest.mutate()}
        onDeleteClick={() => setDeleteOpen(true)}
      />

      {testResult && !testResult.ok ? (
        <div
          className="rounded-md border border-destructive/40 bg-destructive/5 px-4 py-2.5 text-sm text-destructive"
          role="alert"
        >
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
          void qc.invalidateQueries({ queryKey: mcpCapabilitiesKey(name) });
        }}
      />

      <McpServerDeleteDialog
        name={name}
        open={deleteOpen}
        isPending={del.isPending}
        error={del.error}
        onOpenChange={(o) => {
          setDeleteOpen(o);
          if (!o) del.reset();
        }}
        onConfirm={handleDelete}
      />
    </div>
  );
}
