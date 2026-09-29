// frontend/src/pages/McpServerDetailPage.tsx
// One MCP server's detail page. Addressed by the server's NAME (fixed at
// creation, unique among MCP servers) with the open tab in the path
// (`/mcp-servers/<name>/tools`); the REST API addresses a server by uid, so
// the name is resolved against the MCP servers list, and an old uid address
// redirects to the name address.
import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Server } from "lucide-react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import { canonicalDetailPath, resolveByName } from "@/lib/detailTabs";
import { useResource, useResources } from "@/lib/hooks/useResources";
import { useDeleteResource } from "@/lib/hooks/useResourceMutations";
import { useMcpCapabilities } from "@/lib/hooks/useMcpCapabilities";
import { useMcpServerStatus } from "@/lib/hooks/useMcpServerStatus";
import { useTestMcpServer } from "@/lib/hooks/useMcpServerMutations";
import { mcpCapabilitiesKey } from "@/lib/api/queryKeys";
import type { components } from "@/lib/api/types";
import { type HealthState } from "@/components/mcp/HealthBadge";
import { McpServerDetailHeader } from "@/components/mcp/McpServerDetailHeader";
import { McpServerDetailTabs } from "@/components/mcp/McpServerDetailTabs";
import { MCP_SERVER_TABS } from "@/components/mcp/mcpServerTabs";

type TestResult = components["schemas"]["McpTestResultOut"];

export function McpServerDetailPage() {
  const { t } = useTranslation();
  const { name: nameParam = "", tab: pathTab } = useParams<{ name: string; tab?: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const list = useResources("mcp_server");
  const match = resolveByName(list.data, nameParam);
  const uid = match?.item.uid ?? "";
  // When navigated here from an agent's MCP servers tab, location.state carries
  // a return target, so "← back" leads to that agent rather than the list.
  const backState = location.state as { backTo?: string; backLabel?: string } | null;
  const back = backState?.backTo
    ? { to: backState.backTo, label: t("common.backTo", { label: backState.backLabel ?? "" }) }
    : { to: "/mcp-servers", label: t("mcp.server.backToResources") };
  const qc = useQueryClient();
  const { data: resource, isPending, error } = useResource(uid);
  const {
    isPending: capsPending,
    data: capabilities,
    error: capsError,
  } = useMcpCapabilities(uid, !isPending && !error);
  const { data: serverStatus } = useMcpServerStatus(uid);
  const del = useDeleteResource();
  const [deleteOpen, setDeleteOpen] = useState(false);

  const runTest = useTestMcpServer(uid);

  // Derive the test outcome straight from the mutation rather than mirroring
  // it into separate state: a transport failure becomes a failing result.
  const testResult: TestResult | null =
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
    del.mutate({ kind: "mcp_server", uid }, { onSuccess: () => navigate("/mcp-servers") });
  };

  // An old uid address: go to the same tab of the name address.
  if (match?.byUid) {
    return (
      <Navigate
        replace
        state={location.state}
        to={canonicalDetailPath(
          `/mcp-servers/${encodeURIComponent(match.item.name)}`,
          pathTab,
          location.search,
          MCP_SERVER_TABS,
          "overview",
        )}
      />
    );
  }

  if (list.isPending || (!!uid && isPending)) {
    return (
      <Card className="paper-card">
        <CardContent className="py-12 text-center text-muted-foreground">
          {t("common.loading")}
        </CardContent>
      </Card>
    );
  }
  if (list.error || error || !resource) {
    // The translated error is the title when it says more than "not found";
    // a plain not-found is not repeated as its own description.
    const failure = list.error ?? error;
    const title = t("errors.RESOURCE_NOT_FOUND");
    const message = failure ? translateApiError(t, failure) : null;
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
        serverUid={uid}
        basePath={`/mcp-servers/${encodeURIComponent(nameParam)}`}
        capabilities={capabilities}
        capsError={capsError}
        config={resource.config}
        isCapsPending={capsPending}
        onRefresh={() => {
          void qc.invalidateQueries({ queryKey: mcpCapabilitiesKey(uid) });
        }}
      />

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={(o) => {
          setDeleteOpen(o);
          if (!o) del.reset();
        }}
        title={t("mcp.server.deleteConfirmTitle", { name: resource.name })}
        description={t("mcp.server.deleteConfirmBody")}
        confirmLabel={del.isPending ? t("common.deleting") : t("common.delete")}
        pending={del.isPending}
        error={del.error}
        onConfirm={handleDelete}
      />
    </div>
  );
}
