// frontend/src/pages/MemoryDetailPage.tsx — one project's memories, at /memory/projects/<folder>,
// and the global ones at /memory/global (spec memory "Manage memory sync in the web UI and on the command line").
//
// The header is the project's key (or "Global memories") over one line: where
// it is checked out on this machine — or that it is not, so its memories wait
// in the hub, held back — and how many memories it holds. The body lists them
// with their origin agent and machine and, per agent here, what became of the
// copy. There is no action: Coffer never edits a memory's text, and syncing is
// the Memory page's.
import { Brain } from "lucide-react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { sortAgents } from "@/components/agent/agentOrder";
import { DetailNotFound } from "@/components/DetailNotFound";
import { EmptyState } from "@/components/EmptyState";
import { MemoryEntriesTable } from "@/components/memory/MemoryEntriesTable";
import { PageHeader } from "@/components/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { abbreviateHomePath } from "@/lib/agents/display";
import { translateApiError } from "@/lib/api/errors";
import { useMemoryEntries, useMemorySyncState } from "@/lib/hooks/useMemory";

export function MemoryDetailPage() {
  const { t } = useTranslation();
  const folder = useParams<{ folder: string }>().folder;
  const isGlobal = folder === undefined;
  const state = useMemorySyncState();
  const project = isGlobal ? null : state.data?.projects.find((p) => p.folder === folder);
  // Global memories are asked for as project "" — the hub files them under `global/`.
  const key = isGlobal ? "" : (project?.key ?? null);
  const entries = useMemoryEntries(key);

  if (state.isPending) {
    return (
      <div className="flex flex-col gap-6" aria-busy="true">
        <Skeleton className="h-8 w-64" />
      </div>
    );
  }
  if (!isGlobal && !project) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title={t("memory.title")} />
        <DetailNotFound kind="memory" id={folder ?? ""} backTo="/memory" icon={Brain} />
      </div>
    );
  }

  const count = isGlobal ? (state.data?.global_memories ?? 0) : (project?.memories ?? 0);
  const where = isGlobal ? (
    t("memory.detail.global")
  ) : project?.checked_out ? (
    <span className="font-mono text-xs">{abbreviateHomePath(project.checked_out)}</span>
  ) : (
    t("memory.detail.notHere")
  );
  const agentTypes = sortAgents(
    [...new Set((state.data?.agents ?? []).map((a) => a.agent_type))].map((type) => ({ type })),
  ).map((a) => a.type);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={
          isGlobal ? (
            t("memory.projects.global")
          ) : (
            <span className="truncate font-mono">{project?.key}</span>
          )
        }
        subtitle={
          <span className="text-text-muted">
            {where} · {t("memory.detail.memories", { count })}
          </span>
        }
      />
      {entries.error ? (
        <EmptyState
          icon={Brain}
          tone="error"
          title={t("memory.entries.loadFailed")}
          description={translateApiError(t, entries.error)}
        />
      ) : (
        <MemoryEntriesTable
          entries={entries.data ?? []}
          agentTypes={agentTypes}
          machine={state.data?.machine ?? ""}
          isLoading={entries.isPending}
        />
      )}
    </div>
  );
}
