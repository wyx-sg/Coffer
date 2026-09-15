// frontend/src/components/agents/AgentMemoryTab.tsx
// "Memory" tab on the agent detail page, in three sections that mirror the
// Skills and MCP-servers tabs (Coffer-managed vs the agent's own):
//
//   A. Coffer-managed memory — Coffer aggregates every agent's native memory
//      into its own partitions, and an agent reaches those back through the MCP
//      gateway (recall). They are managed on the standalone Memory page, so this
//      tab does not re-list them: the shared CofferGatewayRow points straight
//      there. Knowledge is a different layer with its own page and its own tab
//      pointer — this one must not send the user there.
//   B. Delivery — whether Coffer's session-start hook is installed in THIS
//      agent's own settings (spec memory FR-054/FR-055; whether it has fired is
//      read as events on the Activity page, not guessed at here). The only
//      section here that writes anything, and the only
//      one that is per-agent rather than per-partition: a hook lives in one
//      agent's settings file, so it belongs on that agent's page rather than on
//      the Memory resource page, where it used to render as a list of agents.
//   C. The agent's own memory — the coding agent's OWN native per-project memory
//      stores (e.g. Claude Code's ~/.claude/projects/<project>/memory/), shown
//      read-only as a table of (project, path, item count). A store is a
//      DIRECTORY, so clicking a row opens its own page: a file tree and a
//      read-only preview, where the open / reveal actions live. The table has no
//      per-row menu — a list of stores is for picking one, and what you can do
//      to the one you picked belongs where its contents are visible. This is NOT
//      Coffer knowledge and NOT the CLAUDE.md instructions file; it is the
//      agent's native memory, surfaced so the user can read and open it. Coffer
//      never writes it.
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { CofferGatewayRow } from "@/components/agents/AgentManagedLink";
import { AgentMemoryDelivery } from "@/components/agents/AgentMemoryDelivery";
import { DataTable, type Column } from "@/components/DataTable";
import { Card } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import type { AgentOut } from "@/lib/api/agents";
import type { NativeMemoryStore } from "@/lib/api/agentNativeMemory";
import { useAgentNativeMemory } from "@/lib/hooks/useAgentNativeMemory";

export function AgentMemoryTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const native = useAgentNativeMemory(agent.name);

  const columns: Column<NativeMemoryStore>[] = [
    {
      key: "project",
      header: t("agents.memoryTab.colProject"),
      className: "whitespace-nowrap",
      cell: (s) => <span className="text-sm font-medium">{s.project}</span>,
    },
    {
      key: "path",
      header: t("agents.memoryTab.colPath"),
      // Prefer the real project path; for Codex every row shares one memory_dir,
      // so the cwd in `path` is what distinguishes (and is more useful than the
      // internal memory folder for Claude Code too).
      cell: (s) => (
        <span className="line-clamp-1 max-w-md font-mono text-xs text-muted-foreground">
          {s.path ?? s.memory_dir}
        </span>
      ),
    },
    {
      key: "items",
      header: t("agents.memoryTab.colItems"),
      className: "whitespace-nowrap tabular-nums text-right",
      cell: (s) => <span className="text-muted-foreground">{s.item_count}</span>,
    },
  ];

  return (
    <div className="space-y-3">
      {/* The "managed by Coffer" pointer, in its own box: what the agent reaches
          THROUGH the gateway lives on the Memory page, not here. */}
      <Card className="p-4">
        <CofferGatewayRow
          agentName={agent.name}
          title={t("agents.cofferManaged")}
          hint={t("agents.memoryTab.accessViaGateway")}
          buttonLabel={t("agents.memoryTab.openMemoryPage")}
          onOpen={() => navigate("/memory")}
          notInstalledHint={t("agents.memoryTab.notInstalled")}
        />
      </Card>

      {/* Delivery: whether this agent's own session-start hook is installed. */}
      <AgentMemoryDelivery agentName={agent.name} />

      <Card className="space-y-3 p-4">
        <div className="space-y-1">
          <h3 className="text-sm font-medium text-muted-foreground">{t("agents.agentOwn")}</h3>
          <p className="text-xs text-muted-foreground">{t("agents.memoryTab.nativeHint")}</p>
        </div>

        {native.isPending ? (
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : native.error ? (
          <p className="text-sm text-destructive">{translateApiError(t, native.error)}</p>
        ) : (
          <DataTable
            rows={native.data?.items ?? []}
            columns={columns}
            // Codex rows share one memory_dir, so key by the routed project too.
            rowKey={(s) => `${s.memory_dir}::${s.path ?? s.project}`}
            // The store's identity is its directory, so that is what the page
            // is addressed by; the label rides along only so the heading can
            // say "api" rather than a forty-character slug path.
            onRowClick={(s) =>
              navigate(
                `/agents/${encodeURIComponent(agent.name)}/memory?${new URLSearchParams({
                  dir: s.memory_dir,
                  project: s.path ?? s.project,
                })}`,
              )
            }
            search={{
              accessor: (s) => `${s.project} ${s.path ?? ""} ${s.memory_dir}`,
              placeholder: t("agents.memoryTab.searchPlaceholder"),
            }}
            emptyMessage={t("agents.memoryTab.nativeEmpty")}
          />
        )}
      </Card>
    </div>
  );
}
