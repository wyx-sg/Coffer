// frontend/src/components/agents/AgentMemoryTab.tsx
// "Memory" tab on the agent detail page: a READ-ONLY overview TABLE of every
// memory store (global + per-project), each row showing the store's readable
// name, scope, and fact count. Coffer keeps its own memory format and agents
// access these stores ONLY via the Coffer MCP gateway — the agent page does not
// project a store into the agent's native memory location. Clicking a row opens
// that store's detail page (/memory/:name) — exactly like the Skills and MCP
// tabs. Resource pages manage the store (its facts live there); this tab only
// shows access, mirroring the read-only MCP-servers tab.
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { DataTable, type Column } from "@/components/DataTable";
import { Badge } from "@/components/ui/badge";
import { translateApiError } from "@/lib/api/errors";
import type { AgentOut } from "@/lib/api/agents";
import { projectDirName, type MemoryStoreOut } from "@/kinds/memory/api";
import { useMemoryStores } from "@/lib/hooks/useMemoryStores";

export function AgentMemoryTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const stores = useMemoryStores();

  const rows = (stores.data ?? []) as MemoryStoreOut[];

  const columns: Column<MemoryStoreOut>[] = [
    {
      key: "name",
      header: t("memory.cols.name"),
      // Show the project's directory basename (derived from project_root) as the
      // primary label with the absolute path beneath it, so a per-project store
      // reads as e.g. "coffer" instead of the opaque project-<ULID> name
      // (mirrors MemoryStoresTable). Falls back to the raw store name when the
      // root is unknown (the global store reads as "global").
      cell: (store) => (
        <div className="min-w-0">
          <span className="text-sm font-medium">
            {projectDirName(store.project_root) ?? store.name}
          </span>
          {store.project_root ? (
            <span className="block truncate font-mono text-xs text-muted-foreground">
              {store.project_root}
            </span>
          ) : null}
        </div>
      ),
    },
    {
      key: "scope",
      header: t("memory.cols.scope"),
      className: "whitespace-nowrap",
      cell: (store) => <Badge variant="secondary">{store.scope}</Badge>,
    },
    {
      key: "facts",
      header: t("memory.cols.facts"),
      className: "tabular-nums",
      cell: (store) => <span className="text-muted-foreground">{store.fact_count ?? 0}</span>,
    },
  ];

  return (
    <div className="space-y-3">
      <div className="space-y-1">
        <h3 className="text-sm font-medium text-muted-foreground">{t("agents.memoryTab.title")}</h3>
        <p className="text-xs text-muted-foreground">{t("agents.memoryTab.subtitle")}</p>
        <p className="text-xs text-muted-foreground">{t("agents.memoryTab.accessViaGateway")}</p>
      </div>

      {stores.isPending ? (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : stores.error ? (
        <p className="text-sm text-destructive">{translateApiError(t, stores.error)}</p>
      ) : (
        <DataTable
          rows={rows}
          columns={columns}
          rowKey={(store) => store.name}
          onRowClick={(store) =>
            navigate(`/memory/${store.name}`, {
              state: { backTo: `/agents/${agent.name}`, backLabel: agent.name },
            })
          }
          emptyMessage={t("agents.memoryTab.empty")}
        />
      )}
    </div>
  );
}
