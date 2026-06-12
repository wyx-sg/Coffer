// frontend/src/components/agents/AgentMemoryTab.tsx
// "Memory" tab on the agent detail page: a compact overview TABLE of every
// memory store (global + per-project), each row showing scope, its projection
// state for THIS agent, and a Switch toggling whether the store is PROJECTED
// into this agent's native memory location (symlink for Claude Code, a managed
// AGENTS.md block for Codex). Clicking a row opens that store's detail page
// (/memory/:name) — exactly like the Skills and MCP tabs. Resource pages manage
// the store (its facts live there); the agent page binds it.
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { DataTable, type Column } from "@/components/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import type { AgentOut } from "@/lib/api/agents";
import { getAgentNativeMemory, importAgentNativeMemory } from "@/lib/api/nativeMemory";
import type { MemoryStoreOut } from "@/kinds/memory/api";
import {
  useEstablishProjection,
  useMemoryProjections,
  useMemoryStores,
  useRemoveProjection,
} from "@/lib/hooks/useMemoryProjections";

/** Projection-enabled toggle for a store. Stops propagation so flipping it
 *  doesn't trigger the row's navigate-to-detail click. Keeps the establish /
 *  remove wiring (incl. the project-root contract) from the old row layout. */
function StoreProjectionSwitch({ store, agent }: { store: MemoryStoreOut; agent: AgentOut }) {
  const { t } = useTranslation();
  const projections = useMemoryProjections(store.name);
  const establish = useEstablishProjection(store.name);
  const remove = useRemoveProjection(store.name);

  const projection = (projections.data ?? []).find((p) => p.agent_ref === agent.name);
  const isProjected = Boolean(projection);

  // A project-scoped store's projection must be anchored under its project root
  // (007 contract). The global store needs no root. When a project store has no
  // known root we can't form a well-specified request, so disable the toggle.
  const isProjectScope = store.scope === "project";
  const projectRoot = store.project_root ?? null;
  const missingProjectRoot = isProjectScope && !projectRoot;

  const pending = establish.isPending || remove.isPending;

  const handleToggle = (checked: boolean) => {
    if (checked) {
      if (missingProjectRoot) return;
      establish.mutate(
        isProjectScope ? { agentRef: agent.name, projectRoot } : { agentRef: agent.name },
      );
    } else {
      remove.mutate(agent.name);
    }
  };

  return (
    <Switch
      checked={isProjected}
      onClick={(e) => e.stopPropagation()}
      onCheckedChange={handleToggle}
      disabled={pending || projections.isPending || (missingProjectRoot && !isProjected)}
      title={
        missingProjectRoot && !isProjected ? t("agents.memoryTab.missingProjectRoot") : undefined
      }
      aria-label={t("agents.memoryTab.toggleAria", { store: store.name })}
    />
  );
}

/** Projection mode/target for a store, or a "not projected" hint. */
function StoreProjectionCell({ store, agent }: { store: MemoryStoreOut; agent: AgentOut }) {
  const { t } = useTranslation();
  const projections = useMemoryProjections(store.name);
  const projection = (projections.data ?? []).find((p) => p.agent_ref === agent.name);

  const isProjectScope = store.scope === "project";
  const missingProjectRoot = isProjectScope && !store.project_root;

  if (projection) {
    return (
      <div className="space-y-0.5 text-xs text-muted-foreground">
        <div className="flex items-center gap-2">
          <Badge variant="outline">{projection.projection_mode}</Badge>
          <span className="line-clamp-1 max-w-xs break-all font-mono">
            {projection.target_path}
          </span>
        </div>
        {projection.native_memory_disabled ? (
          <div>{t("agents.memoryTab.nativeDisabled")}</div>
        ) : null}
        {projection.merged_existing ? <div>{t("agents.memoryTab.merged")}</div> : null}
      </div>
    );
  }
  return (
    <span className="text-xs text-muted-foreground">
      {missingProjectRoot
        ? t("agents.memoryTab.missingProjectRoot")
        : t("agents.memoryTab.notProjected")}
    </span>
  );
}

function NativeMemoryBanner({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const native = useQuery({
    queryKey: ["agent-native-memory", agent.name],
    queryFn: () => getAgentNativeMemory(agent.name),
  });
  const takeover = useMutation({
    mutationFn: () => importAgentNativeMemory(agent.name),
    onSuccess: () => {
      // The takeover provisions stores + projections and flips dirs to managed;
      // refresh every view that reflects that state.
      void qc.invalidateQueries({ queryKey: ["agent-native-memory", agent.name] });
      void qc.invalidateQueries({ queryKey: ["memory-stores"] });
      void qc.invalidateQueries({ queryKey: ["memory-projections"] });
      void qc.invalidateQueries({ queryKey: ["memory-facts"] });
    },
  });
  const count = native.data?.unmanaged_fact_count ?? 0;
  if (count === 0) return null;
  const projects = (native.data?.projects ?? []).filter((p) => !p.managed).length;
  return (
    <div className="space-y-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-sm">
      <div className="flex items-center justify-between gap-3">
        <p>{t("agents.memoryTab.nativeDiscovered", { count, projects })}</p>
        <Button size="sm" onClick={() => takeover.mutate()} disabled={takeover.isPending}>
          {takeover.isPending
            ? t("agents.memoryTab.takingOver")
            : t("agents.memoryTab.takeOver")}
        </Button>
      </div>
      {takeover.error ? (
        <p className="text-xs text-destructive">{translateApiError(t, takeover.error)}</p>
      ) : null}
      {takeover.data ? (
        <p className="text-xs text-muted-foreground">
          {t("agents.memoryTab.takeOverDone", {
            imported: takeover.data.imported,
            skipped: takeover.data.skipped,
          })}
        </p>
      ) : null}
    </div>
  );
}

export function AgentMemoryTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const stores = useMemoryStores();

  const rows = (stores.data ?? []) as MemoryStoreOut[];

  const columns: Column<MemoryStoreOut>[] = [
    {
      key: "name",
      header: t("memory.cols.name"),
      className: "whitespace-nowrap",
      cell: (store) => <span className="text-sm font-medium">{store.name}</span>,
    },
    {
      key: "scope",
      header: t("memory.cols.scope"),
      className: "whitespace-nowrap",
      cell: (store) => <Badge variant="secondary">{store.scope}</Badge>,
    },
    {
      key: "projection",
      header: t("agents.memoryTab.colProjection"),
      cell: (store) => <StoreProjectionCell store={store} agent={agent} />,
    },
    {
      key: "enabled",
      header: t("agents.memoryTab.colEnabled"),
      className: "text-right",
      cell: (store) => <StoreProjectionSwitch store={store} agent={agent} />,
    },
  ];

  return (
    <div className="space-y-3">
      <div className="space-y-1">
        <h3 className="text-sm font-medium text-muted-foreground">{t("agents.memoryTab.title")}</h3>
        <p className="text-xs text-muted-foreground">{t("agents.memoryTab.subtitle")}</p>
      </div>

      <NativeMemoryBanner agent={agent} />

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
