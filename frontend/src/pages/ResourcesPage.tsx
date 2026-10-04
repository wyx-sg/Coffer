// frontend/src/pages/ResourcesPage.tsx — the MCP servers page (design 4.1; spec web-ui "Lay out every detail page's tabs alike").
//
// The list beside the open server, like the Skills page, at `/mcp-servers[/<name>[/<tab>]]`:
// the servers grouped by what needs the user (McpServerList), the open server
// (McpServerPane) or Coffer's own built-in one (McpBuiltinPane, name `coffer`),
// the full-width first-run welcome, or a prompt to choose one. One header
// action, Add server. Scoped to `mcp_server` server-side. (The file keeps its old
// name — the naming exception in .agents/frontend.md.) A server is addressed by
// its fixed NAME.
import { lazy, Suspense, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Plus, Server } from "lucide-react";

import { DetailNotFound } from "@/components/DetailNotFound";
import { NothingSelected } from "@/components/ListPaneStates";
import { PageHeader } from "@/components/PageHeader";
import { SplitView } from "@/components/SplitView";
import { AddMcpServerDialog } from "@/components/mcp/AddMcpServerDialog";
import { McpFirstRun } from "@/components/mcp/server/McpFirstRun";
import { McpSelectionPane } from "@/components/mcp/server/McpSelectionPane";
import { BUILTIN_NAME, McpServerList } from "@/components/mcp/server/McpServerList";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { isCustomToolGroup } from "@/lib/customTools/groups";
import { useDaemonEvents } from "@/lib/hooks/useDaemonEvents";
import { useResources } from "@/lib/hooks/useResources";
import { PAGE_BLEED, PAGE_BLEED_HEAD } from "@/components/shell/pageFrame";
import { cn } from "@/lib/utils";

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
  const navigate = useNavigate();
  const list = useResources("mcp_server");
  const [add, setAdd] = useState<"paste" | "importAgents" | null>(null);
  // The servers ticked in the list; while any is, the right pane summarises them (board 4.1.28).
  const [picked, setPicked] = useState<ReadonlySet<string>>(new Set());
  useDaemonEvents();

  // Custom-tool groups are `mcp_server`s too, but they live on the Custom
  // tools page (spec web-ui "Manage custom tools on their own page"); an
  // address naming one goes there.
  const all = list.data ?? [];
  const servers = all.filter((r) => !isCustomToolGroup(r));
  const match = nameParam ? servers.find((r) => r.name === nameParam) : undefined;
  const basePath = `/mcp-servers/${encodeURIComponent(nameParam)}`;
  const group = nameParam
    ? all.find((r) => isCustomToolGroup(r) && r.name === nameParam)
    : undefined;
  if (group) {
    return <Navigate replace to={`/custom-tools/${encodeURIComponent(group.name)}`} />;
  }

  const tabSegment = pathTab && pathTab !== "overview" ? `/${pathTab}` : "";
  const hrefFor = (name: string) => `/mcp-servers/${encodeURIComponent(name)}${tabSegment}`;

  // Nothing registered: the welcome takes the page's whole width, no list (board 4.1.20).
  const firstRun = !list.error && !list.isPending && servers.length === 0 && !nameParam;
  // While the list loads or failed (its pane shows why), the right pane stays empty.
  const selected = servers.filter((r) => picked.has(r.uid));
  let pane: JSX.Element | null;
  if (list.error || list.isPending) {
    pane = null;
  } else if (selected.length > 1) {
    pane = <McpSelectionPane servers={selected} onDone={() => setPicked(new Set())} />;
  } else if (match) {
    pane = (
      <Suspense fallback={<PaneSkeleton />}>
        <McpServerPane
          key={match.uid}
          resource={match}
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
    pane = <DetailNotFound kind="mcp" id={nameParam} backTo="/mcp-servers" icon={Server} />;
  } else if (servers.length === 0) {
    pane = <McpFirstRun onImport={() => setAdd("importAgents")} />;
  } else {
    pane = <NothingSelected icon={Server} />;
  }

  return (
    // Full-bleed like the Skills page: a workspace whose two panes each scroll.
    <div className={cn(PAGE_BLEED, "flex-col")}>
      <div className={cn(PAGE_BLEED_HEAD, "shrink-0 border-b border-border-subtle pb-4")}>
        <PageHeader
          title={t("resources.title")}
          subtitle={t("resources.subtitle")}
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
              error={list.error}
              onRetry={() => void list.refetch()}
              selectedName={selected.length > 1 ? null : (match?.name ?? null)}
              hrefFor={hrefFor}
              builtinSelected={selected.length < 2 && !match && nameParam === BUILTIN_NAME}
              picked={picked}
              onPickedChange={setPicked}
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
