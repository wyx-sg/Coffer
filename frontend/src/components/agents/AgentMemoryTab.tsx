// frontend/src/components/agents/AgentMemoryTab.tsx — spec agent-registry
// "Read one native memory store's files read-only".
// The agent detail page's Memory tab: the coding agent's OWN native memory
// stores (Claude Code's ~/.claude/projects/<project>/memory/, Codex's
// ~/.codex/memories/MEMORY.md sliced by project), read-only, as one table of
// project, path and item count. Coffer reads them to build shared memory and
// never writes them; the shared memory itself, and how it reaches agents, is
// the Memory page's.
//
// A store is a directory, so a row opens its own page (a file tree and a
// read-only preview, where the open / reveal actions live) — the table has no
// per-row actions.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Brain, ChevronRight } from "lucide-react";

import { DataTable, type Column } from "@/components/DataTable";
import { TruncatedPath, TruncatedText } from "@/components/ui/truncated-text";
import { SearchInput } from "@/components/SearchInput";
import { Section } from "@/components/Section";
import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import { agentMemoryStorePath } from "@/lib/agents/routes";
import type { AgentOut } from "@/lib/api/agents";
import type { NativeMemoryStore } from "@/lib/api/agentNativeMemory";
import { translateApiError } from "@/lib/api/errors";
import { useAgentNativeMemory } from "@/lib/hooks/useAgentNativeMemory";

/** Where the agent writes its memory, for the empty state. */
function memoryLocation(agent: AgentOut): string {
  const dir = abbreviateHomePath(agent.config_dir);
  return agent.type === "codex" ? `${dir}/memories/MEMORY.md` : `${dir}/projects/<project>/memory/`;
}

/** The project a store belongs to: its real directory when Coffer resolved one. */
function projectLabel(store: NativeMemoryStore): string {
  return store.path ? abbreviateHomePath(store.path) : store.project;
}

export function AgentMemoryTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const native = useAgentNativeMemory(agent.uid);
  const agentName = agentTypeLabel(agent.type);
  const [query, setQuery] = useState("");
  // A store with no memory in it (a scratch project the agent once ran in) is not
  // worth a row; the rest are searched by project name or path.
  const all = useMemo(
    () => (native.data?.items ?? []).filter((s) => s.item_count > 0),
    [native.data],
  );
  const stores = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q
      ? all.filter((s) => `${projectLabel(s)} ${s.memory_dir}`.toLowerCase().includes(q))
      : all;
  }, [all, query]);

  if (native.error) {
    return (
      <EmptyState
        icon={Brain}
        tone="error"
        title={t("agents.memoryTab.loadFailed")}
        description={translateApiError(t, native.error)}
        action={
          <Button variant="outline" size="sm" onClick={() => void native.refetch()}>
            {t("common.retry")}
          </Button>
        }
      />
    );
  }
  if (!native.isPending && all.length === 0) {
    return (
      <EmptyState
        icon={Brain}
        title={t("agents.memoryTab.emptyTitle", { agent: agentName })}
        description={t("agents.memoryTab.emptyBody", {
          agent: agentName,
          path: memoryLocation(agent),
        })}
      />
    );
  }

  const columns: Column<NativeMemoryStore>[] = [
    {
      key: "project",
      header: t("agents.memoryTab.colProject"),
      className: "w-[34%]",
      cell: (s) => <TruncatedText text={projectLabel(s)} className="text-sm text-text" />,
    },
    {
      key: "path",
      header: t("agents.memoryTab.colPath"),
      cell: (s) => (
        <TruncatedPath
          text={abbreviateHomePath(s.memory_dir)}
          className="text-xs text-text-muted"
        />
      ),
    },
    {
      key: "items",
      header: t("agents.memoryTab.colItems"),
      className: "w-[80px] whitespace-nowrap text-right tabular-nums",
      cell: (s) => <span className="text-text-muted">{s.item_count}</span>,
    },
    {
      key: "open",
      header: <span className="sr-only">{t("agents.memoryTab.open")}</span>,
      className: "w-10",
      cell: () => <ChevronRight className="size-4 text-text-subtle" aria-hidden />,
    },
  ];

  return (
    <Section
      title={t("agents.memoryTab.title")}
      help={t("agents.memoryTab.subtitle")}
      actions={
        <SearchInput
          value={query}
          onChange={setQuery}
          placeholder={t("agents.memoryTab.search")}
          ariaLabel={t("agents.memoryTab.search")}
          className="w-64"
        />
      }
    >
      <DataTable
        fixed
        rows={stores}
        columns={columns}
        isLoading={native.isPending}
        // Codex rows share one memory_dir, so key by the routed project too.
        rowKey={(s) => `${s.memory_dir}::${s.path ?? s.project}`}
        onRowClick={(s) =>
          navigate(agentMemoryStorePath(agent.type, s.memory_dir, s.path ?? s.project))
        }
        emptyMessage={t("agents.memoryTab.noMatch")}
      />
    </Section>
  );
}
