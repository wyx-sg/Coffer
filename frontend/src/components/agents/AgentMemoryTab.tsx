// frontend/src/components/agents/AgentMemoryTab.tsx
// "Memory" tab on the agent detail page, in two read-only sections that mirror
// the Skills and MCP-servers tabs (Coffer-managed vs the agent's own):
//
//   A. Coffer-managed knowledge — Coffer keeps its own knowledge layer and
//      agents reach it ONLY via the MCP gateway. It is managed on the standalone
//      Knowledge page, so this tab does not re-list it: the shared
//      CofferGatewayRow points straight there.
//   B. The agent's own memory — the coding agent's OWN native per-project memory
//      stores (e.g. Claude Code's ~/.claude/projects/<project>/memory/), shown
//      read-only as a table of (project, path, item count) with open / reveal
//      row actions. This is NOT Coffer knowledge and NOT the CLAUDE.md
//      instructions file; it is the agent's native memory, surfaced so the user
//      can find and open it. Coffer never writes it.
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { CofferGatewayRow } from "@/components/agents/AgentManagedLink";
import { DataTable, type Column } from "@/components/DataTable";
import { RowActions } from "@/components/RowActions";
import { Card } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import type { AgentOut } from "@/lib/api/agents";
import type { NativeMemoryStore } from "@/lib/api/agentNativeMemory";
import { useFileActionItems } from "@/lib/fileActionItems";
import { useAgentNativeMemory } from "@/lib/hooks/useAgentNativeMemory";

/** Row actions: open the store's directory in the user's editor, or reveal it in
 * the file manager. Both go through the daemon; the row itself does nothing
 * else, because this surface is read-only. */
function NativeMemoryRowActions({ store }: { store: NativeMemoryStore }) {
  const { t } = useTranslation();
  const fileItems = useFileActionItems(store.memory_dir);
  return <RowActions items={fileItems} menuAriaLabel={t("common.moreActions")} />;
}

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
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (s) => <NativeMemoryRowActions store={s} />,
    },
  ];

  return (
    <div className="space-y-3">
      {/* The "managed by Coffer" pointer, in its own box: what the agent reaches
          THROUGH the gateway lives on the Knowledge page, not here. */}
      <Card className="p-4">
        <CofferGatewayRow
          agentName={agent.name}
          title={t("agents.cofferManaged")}
          hint={t("agents.memoryTab.accessViaGateway")}
          buttonLabel={t("agents.memoryTab.openMemoryPage")}
          onOpen={() => navigate("/knowledge")}
          notInstalledHint={t("agents.memoryTab.notInstalled")}
        />
      </Card>

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
