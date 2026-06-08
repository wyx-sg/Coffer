// frontend/src/components/agents/AgentMemoryTab.tsx
// "Memory" tab on the agent detail page: lists each memory store (global +
// per-project) and lets the user toggle whether this store is PROJECTED into
// this agent's native memory location (symlink for Claude Code, a managed
// AGENTS.md block for Codex). The projection status (mode + target path +
// whether native memory was disabled) is shown when established. Resource
// pages manage the store; the agent page binds it — matching the skills tab.
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import type { AgentOut } from "@/lib/api/agents";
import type { MemoryStoreOut } from "@/kinds/memory/api";
import {
  useEstablishProjection,
  useMemoryProjections,
  useMemoryStores,
  useRemoveProjection,
} from "@/lib/hooks/useMemoryProjections";

function StoreProjectionRow({ store, agent }: { store: MemoryStoreOut; agent: AgentOut }) {
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
    <li className="flex items-start justify-between gap-3 p-3">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">{store.name}</span>
          <Badge variant="secondary">{store.scope}</Badge>
          {projection ? <Badge variant="outline">{projection.projection_mode}</Badge> : null}
        </div>
        {projection ? (
          <div className="space-y-0.5 text-xs text-muted-foreground">
            <div className="font-mono break-all">{projection.target_path}</div>
            {projection.native_memory_disabled ? (
              <div>{t("agents.memoryTab.nativeDisabled")}</div>
            ) : null}
            {projection.merged_existing ? <div>{t("agents.memoryTab.merged")}</div> : null}
          </div>
        ) : (
          <div className="text-xs text-muted-foreground">{t("agents.memoryTab.notProjected")}</div>
        )}
        {missingProjectRoot ? (
          <p className="text-xs text-muted-foreground">
            {t("agents.memoryTab.missingProjectRoot")}
          </p>
        ) : null}
        {establish.error ? (
          <p className="text-xs text-destructive">{translateApiError(t, establish.error)}</p>
        ) : null}
        {remove.error ? (
          <p className="text-xs text-destructive">{translateApiError(t, remove.error)}</p>
        ) : null}
      </div>
      <Switch
        checked={isProjected}
        onCheckedChange={handleToggle}
        disabled={pending || projections.isPending || (missingProjectRoot && !isProjected)}
        title={
          missingProjectRoot && !isProjected ? t("agents.memoryTab.missingProjectRoot") : undefined
        }
        aria-label={t("agents.memoryTab.toggleAria", { store: store.name })}
      />
    </li>
  );
}

export function AgentMemoryTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const stores = useMemoryStores();

  return (
    <div className="space-y-3">
      <div className="space-y-1">
        <h3 className="text-sm font-medium text-muted-foreground">{t("agents.memoryTab.title")}</h3>
        <p className="text-xs text-muted-foreground">{t("agents.memoryTab.subtitle")}</p>
      </div>

      {stores.isPending ? (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : stores.error ? (
        <p className="text-sm text-destructive">{translateApiError(t, stores.error)}</p>
      ) : (stores.data ?? []).length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("agents.memoryTab.empty")}</p>
      ) : (
        <ul className="divide-y rounded border">
          {(stores.data ?? []).map((store) => (
            <StoreProjectionRow key={store.name} store={store} agent={agent} />
          ))}
        </ul>
      )}
    </div>
  );
}
