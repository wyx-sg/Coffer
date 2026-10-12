// frontend/src/pages/MemoryPage.tsx — the Memory page: what the person's agents remembered, kept in sync between them
// (spec memory "Manage memory sync in the web UI and on the command line").
//
// Coffer keeps every memory an agent wrote for itself in a hub in the vault and
// writes each one into the person's other agents, in their own memory format;
// each agent curates and loads its memory itself. The memories are the page:
// the header carries Sync now (its ▾ holds the automatic sync's switch and
// interval), when memory last synced and syncs next, and a ⋯ menu with Undo
// sync…; under it one banner counts what waits on the person (a first or large
// sync to confirm, a source the last sync could not read, a memory it
// withheld, an agent whose own memory is off so nothing is written into it).
// Each agent's own memory and curation live on its Memory tab. Below, the
// scopes — global memories, then the hub's projects — beside the open scope's
// memories (`?scope=`); a memory opens in a drawer
// (`?memory=<id>`) with its text and where each agent holds it. Nothing on the
// page edits a memory's text: the person edits memory in the agent's own
// memory directory.
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Brain, Undo2 } from "lucide-react";

import { NothingSelected } from "@/components/ListPaneStates";
import { MemoryDrawer } from "@/components/memory/MemoryDrawer";
import { MemoryList } from "@/components/memory/MemoryList";
import { MemoryPageEmpty } from "@/components/memory/MemoryPageEmpty";
import { MemoryNeedsYou } from "@/components/memory/MemoryNeedsYou";
import { MemoryScopeList } from "@/components/memory/MemoryScopeList";
import { MemorySyncButton } from "@/components/memory/MemorySyncButton";
import { MemorySyncClock } from "@/components/memory/MemorySyncClock";
import { UndoSyncDialog } from "@/components/memory/UndoSyncDialog";
import { PageHeader } from "@/components/PageHeader";
import { SplitView } from "@/components/SplitView";
import { PAGE_BLEED, PAGE_BLEED_HEAD } from "@/components/shell/pageFrame";
import { ActionMenu } from "@/components/ui/menu";
import { useMemoryEntries, useMemorySyncState } from "@/lib/hooks/useMemory";
import {
  GLOBAL_SCOPE,
  defaultScope,
  parsePreview,
  reportFailures,
  reportWithheld,
} from "@/lib/memory/syncFacts";
import { cn } from "@/lib/utils";

export function MemoryPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const { data: state, isPending, error, refetch } = useMemorySyncState();
  const [undoing, setUndoing] = useState(false);
  const agents = state?.agents ?? [];
  const noAgents = Boolean(state) && agents.length === 0;

  const scope = params.get("scope") ?? (state ? defaultScope(state) : null);
  const isGlobal = scope === GLOBAL_SCOPE;
  const project = isGlobal ? null : (state?.projects.find((p) => p.folder === scope) ?? null);
  const known = isGlobal || project !== null;
  // Global memories are asked for as project "" — the hub files them under `global/`.
  const entries = useMemoryEntries(isGlobal ? "" : (project?.key ?? null));
  const rows = useMemo(() => entries.data ?? [], [entries.data]);

  const openId = params.get("memory");
  const openIndex = openId ? rows.findIndex((e) => e.id === openId) : -1;
  const open = openIndex >= 0 ? rows[openIndex] : null;
  const setOpen = (id: string | null) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (scope) next.set("scope", scope);
        if (id) next.set("memory", id);
        else next.delete("memory");
        return next;
      },
      { replace: id !== null && openId !== null },
    );

  // A stale `?memory=` (synced away) closes the drawer instead of leaving it empty.
  useEffect(() => {
    if (openId && entries.data && openIndex < 0) setOpen(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openId, entries.data, openIndex]);

  const stepping = {
    onPrevious: () => openIndex > 0 && setOpen(rows[openIndex - 1].id),
    onNext: () => openIndex < rows.length - 1 && setOpen(rows[openIndex + 1].id),
    hasPrevious: openIndex > 0,
    hasNext: openIndex >= 0 && openIndex < rows.length - 1,
  };

  let pane: JSX.Element | null = null;
  if (state && known) {
    pane = (
      <MemoryList
        key={scope}
        project={project}
        count={isGlobal ? state.global_memories : (project?.memories ?? 0)}
        entries={rows}
        machine={state.machine}
        isLoading={entries.isPending}
        onOpen={(e) => setOpen(e.id)}
        source={params.get("source")}
      />
    );
  } else if (state) {
    pane = <NothingSelected icon={Brain} />;
  }

  return (
    <div className={cn(PAGE_BLEED, "flex-col")}>
      <div className={cn(PAGE_BLEED_HEAD, "flex shrink-0 flex-col gap-4 pb-4")}>
        <PageHeader
          title={t("memory.title")}
          experimental
          subtitle={
            state ? (
              <MemorySyncClock lastSyncedAt={state.last_synced_at} running={state.running} />
            ) : (
              t("memory.subtitle")
            )
          }
          actions={
            state && !noAgents ? (
              <>
                <MemorySyncButton running={state.running} />
                <ActionMenu
                  label={t("memory.moreActions")}
                  actions={[
                    {
                      key: "undo",
                      label: t("memory.undo.menu"),
                      description: t("memory.undo.menuDescription"),
                      icon: Undo2,
                      destructive: true,
                      onSelect: () => setUndoing(true),
                    },
                  ]}
                />
              </>
            ) : null
          }
        />
        {state && !noAgents ? (
          <MemoryNeedsYou
            preview={parsePreview(state.preview)}
            failures={reportFailures(state.last_report)}
            withheld={reportWithheld(state.last_report)}
            agents={agents}
            onOpenMemory={(entry, key) => {
              const folder = key
                ? state.projects.find((p) => p.key === key)?.folder
                : GLOBAL_SCOPE;
              if (folder) setParams({ scope: folder, memory: entry });
            }}
          />
        ) : null}
      </div>

      {error || noAgents ? (
        <MemoryPageEmpty error={error} onRetry={() => void refetch()} />
      ) : (
        <SplitView
          storageKey="memory.scopes"
          defaultListWidth={260}
          label={t("splitView.resizeList")}
          className="min-h-0 flex-1 border-t border-border-subtle"
          listClassName="bg-surface-sidebar"
          detailClassName="overflow-y-auto"
          list={
            <MemoryScopeList
              projects={state?.projects ?? []}
              globalMemories={state?.global_memories ?? 0}
              selected={scope}
              isLoading={isPending}
            />
          }
          detail={<div className="px-7 pb-5 pt-5">{pane}</div>}
        />
      )}

      <MemoryDrawer
        entry={open}
        machine={state?.machine ?? ""}
        onClose={() => setOpen(null)}
        {...stepping}
      />
      <UndoSyncDialog open={undoing} onOpenChange={setUndoing} agents={agents} />
    </div>
  );
}
