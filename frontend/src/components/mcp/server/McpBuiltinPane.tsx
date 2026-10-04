// src/components/mcp/server/McpBuiltinPane.tsx — Coffer's own `coffer` server, read-only (board 4.1.23 Mcp-Builtin; spec web-ui "Show the built-in coffer server read-only").
//
// Not a registered resource: everything comes from `GET /mcp/builtin`, which
// the daemon builds from the gateway's built-in tool list. The header has no
// Test, Edit or ⋯ menu and its reach is a fixed chip — every connected agent
// gets it. The Overview is the last 24 hours and its tools, which are always
// on; there is no banner and no box explaining what cannot be changed.
import { Server } from "lucide-react";
import { useTranslation } from "react-i18next";

import { StatusPill } from "@/components/status/StatusPill";
import { Skeleton } from "@/components/ui/skeleton";
import { useAgents } from "@/lib/hooks/useAgents";
import { useBuiltinMcpServer } from "@/lib/hooks/useMcpAddFlow";
import { McpServerDetailTabs } from "../McpServerDetailTabs";
import { McpBuiltinTools } from "./McpBuiltinTools";
import { McpCallsLog } from "./McpCallsLog";
import { McpOverviewTab } from "./McpOverviewTab";
import type { ServerState } from "@/lib/mcp/serverState";

const HEALTHY: ServerState = { kind: "healthy", group: "healthy", tone: "ok" };

function NothingHere({ text }: { text: string }) {
  return <p className="py-6 text-sm text-text-muted">{text}</p>;
}

export function McpBuiltinPane({ basePath }: { basePath: string }) {
  const { t } = useTranslation();
  const { data: agents = [] } = useAgents();
  const builtin = useBuiltinMcpServer();
  const server = builtin.data;

  if (!server) {
    return (
      <div className="flex flex-col gap-3" aria-busy={builtin.isPending}>
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-4" data-testid="mcp-builtin-pane">
      <header className="flex min-w-0 items-center gap-3">
        <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-lg bg-surface-sunken text-text-muted">
          <Server className="size-4" strokeWidth={1.75} aria-hidden />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <div className="flex min-w-0 items-center gap-2">
            <h1 className="min-w-0 truncate font-mono text-lg font-semibold">{server.name}</h1>
            <StatusPill tone="ok">{t("mcp.page.state.healthy")}</StatusPill>
            <span className="rounded-sm bg-chip px-1.5 py-0.5 text-2xs font-semibold text-text-muted">
              {t("mcp.builtin.badge")}
            </span>
          </div>
          <p className="min-w-0 truncate text-xs text-text-muted" data-visual-volatile>
            {t("mcp.page.transport.http")} · <span className="font-mono">{server.url}</span> ·{" "}
            {t("mcp.builtin.servedBy")}
          </p>
        </div>
        <span className="shrink-0 rounded-md border border-border-subtle bg-surface-sunken px-2.5 py-1 text-xs font-label text-text">
          {t("mcp.builtin.reach")}
        </span>
      </header>
      <McpServerDetailTabs
        basePath={basePath}
        overview={
          <McpOverviewTab
            invocationsHref={`${basePath}/invocations`}
            name={server.name}
            enabled
            builtin
            state={HEALTHY}
            agents={agents}
            summary={server.summary}
            summaryPending={false}
            tools={<McpBuiltinTools tools={server.tools} summary={server.summary} top />}
          />
        }
        tools={<McpBuiltinTools tools={server.tools} summary={server.summary} />}
        resources={<NothingHere text={t("mcp.builtin.noResources")} />}
        prompts={<NothingHere text={t("mcp.builtin.noPrompts")} />}
        invocations={
          <McpCallsLog
            serverUid={server.invocation_uid}
            serverName={server.name}
            transport="http"
            agents={agents}
            builtin
          />
        }
      />
    </div>
  );
}
