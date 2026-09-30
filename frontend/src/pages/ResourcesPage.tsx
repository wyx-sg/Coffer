// frontend/src/pages/ResourcesPage.tsx — the MCP servers page (design 4.1; spec web-ui "Lay out every detail page's tabs alike").
//
// The list beside the open server, like the Skills page, at `/mcp-servers[/<name>[/<tab>]]`:
// the servers grouped by what needs the user (McpServerList), the open server
// (McpServerPane) or Coffer's own built-in one (McpBuiltinPane, name `coffer`),
// the full-width first-run welcome, or a prompt to choose one. One header
// action, Add server. Scoped to `mcp_server` server-side. (The file keeps its old
// name — the naming exception in .agents/frontend.md.) A server is addressed by
// its fixed NAME; `/mcp-servers/<uid>` and an old `?tab=` redirect to it.
import { lazy, Suspense, useState } from "react";
import { Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Plus, Server } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { HelpTip } from "@/components/HelpTip";
import { PageHeader } from "@/components/PageHeader";
import { SplitView } from "@/components/SplitView";
import { AddMcpServerDialog } from "@/components/mcp/AddMcpServerDialog";
import { MCP_SERVER_TABS } from "@/components/mcp/mcpServerTabs";
import { McpFirstRun } from "@/components/mcp/server/McpFirstRun";
import { BUILTIN_NAME, McpServerList } from "@/components/mcp/server/McpServerList";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { isCustomToolGroup } from "@/lib/customTools/groups";
import { canonicalDetailPath, resolveByName } from "@/lib/detailTabs";
import { useDaemonEvents } from "@/lib/hooks/useDaemonEvents";
import { useResources } from "@/lib/hooks/useResources";

/** The pane's shape while the list or the pane's code loads — never a bare "Loading…". */
function PaneSkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-busy="true">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-16 w-full" />
      <Skeleton className="h-40 w-full" />
    </div>
  );
}

const McpBuiltinPane = lazy(() =>
  import("@/components/mcp/server/McpBuiltinPane").then((m) => ({ default: m.McpBuiltinPane })),
);

const McpServerPane = lazy(() =>
  import("@/components/mcp/server/McpServerPane").then((m) => ({ default: m.McpServerPane })),
);

export function ResourcesPage() {
  const { t } = useTranslation();
  const { name: nameParam = "", tab: pathTab } = useParams<{ name?: string; tab?: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const list = useResources("mcp_server");
  const [add, setAdd] = useState<"paste" | "importAgents" | null>(null);
  useDaemonEvents();

  // Custom-tool groups are `mcp_server`s too, but they live on the Custom
  // tools page (spec web-ui "Manage custom tools on their own page"); an
  // address naming one goes there.
  const all = list.data ?? [];
  const servers = all.filter((r) => !isCustomToolGroup(r));
  const match = resolveByName(list.data ? servers : undefined, nameParam);
  const basePath = `/mcp-servers/${encodeURIComponent(nameParam)}`;
  const group = nameParam
    ? all.find((r) => isCustomToolGroup(r) && (r.name === nameParam || r.uid === nameParam))
    : undefined;
  if (group) {
    return <Navigate replace to={`/custom-tools/${encodeURIComponent(group.name)}`} />;
  }

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

  const tabSegment = pathTab && pathTab !== "overview" ? `/${pathTab}` : "";
  const hrefFor = (name: string) => `/mcp-servers/${encodeURIComponent(name)}${tabSegment}`;

  // Nothing registered: the welcome takes the page's whole width, no list (board 4.1.20).
  const firstRun = !list.error && !list.isPending && servers.length === 0 && !nameParam;
  let pane: JSX.Element;
  if (list.error) {
    pane = (
      <EmptyState
        tone="error"
        icon={Server}
        title={t("resources.loadFailed")}
        description={translateApiError(t, list.error)}
        action={
          <Button variant="outline" onClick={() => void list.refetch()}>
            {t("common.retry")}
          </Button>
        }
      />
    );
  } else if (list.isPending) {
    pane = <PaneSkeleton />;
  } else if (match) {
    pane = (
      <Suspense fallback={<PaneSkeleton />}>
        <McpServerPane
          key={match.item.uid}
          resource={match.item}
          basePath={basePath}
          onDeleted={() => navigate("/mcp-servers", { replace: true })}
        />
      </Suspense>
    );
  } else if (nameParam === BUILTIN_NAME) {
    // Coffer's own server is not a resource; its pane reads the daemon's description.
    pane = (
      <Suspense fallback={<PaneSkeleton />}>
        <McpBuiltinPane basePath={basePath} />
      </Suspense>
    );
  } else if (nameParam) {
    pane = (
      <EmptyState
        icon={Server}
        title={t("errors.RESOURCE_NOT_FOUND")}
        description={t("mcp.page.notFound", { name: nameParam })}
      />
    );
  } else if (servers.length === 0) {
    pane = <McpFirstRun onAdd={() => setAdd("paste")} onImport={() => setAdd("importAgents")} />;
  } else {
    pane = (
      <EmptyState
        icon={Server}
        title={t("mcp.page.choose.title")}
        description={t("mcp.page.choose.body")}
      />
    );
  }

  return (
    // Full-bleed like the Skills page: a workspace whose two panes each scroll.
    <div className="-mx-6 -my-10 flex h-screen flex-col overflow-hidden md:-mx-10">
      <div className="shrink-0 border-b border-border-subtle px-6 pb-4 pt-5">
        <PageHeader
          title={t("resources.title")}
          badges={
            <>
              {list.data ? <span className="text-sm text-text-muted">{servers.length}</span> : null}
              <HelpTip>
                <p className="text-xs text-text-muted">{t("resources.subtitle")}</p>
              </HelpTip>
            </>
          }
          actions={
            <Button onClick={() => setAdd("paste")}>
              <Plus aria-hidden /> {t("resources.addServer")}
            </Button>
          }
        />
      </div>
      {firstRun ? (
        <div className="min-h-0 flex-1 overflow-y-auto px-7 pb-5">{pane}</div>
      ) : (
        <SplitView
          storageKey="mcp.list"
          defaultListWidth={320}
          label={t("splitView.resizeList")}
          className="min-h-0 flex-1"
          detailClassName="overflow-y-auto"
          list={
            <McpServerList
              servers={servers}
              isLoading={list.isPending}
              selectedName={match?.item.name ?? null}
              hrefFor={hrefFor}
              builtinSelected={!match && nameParam === BUILTIN_NAME}
            />
          }
          detail={<div className="px-7 pb-5 pt-5">{pane}</div>}
        />
      )}
      <AddMcpServerDialog
        open={add !== null}
        initialMode={add ?? "paste"}
        onOpenChange={(open) => (open ? undefined : setAdd(null))}
      />
    </div>
  );
}
