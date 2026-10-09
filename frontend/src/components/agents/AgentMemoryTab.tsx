// frontend/src/components/agents/AgentMemoryTab.tsx — spec agent-registry
// "Read one native memory store's files read-only".
// The agent detail page's Memory tab (boards 2.1.49–50): the agent's own
// memory, its native stores (Claude Code's ~/.claude/projects/<project>/memory/,
// Codex's ~/.codex/memories/MEMORY.md sliced by project), read-only, one
// bordered table (Project · Memory folder · Files). A store is a directory, so
// a row opens its own page (a file tree and a read-only preview). What Coffer
// syncs between the agents is on the Memory page.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { ChevronRight } from "lucide-react";

import { TabEmpty } from "./tabs/TabEmpty";
import { LoadError } from "@/components/LoadError";
import { SearchInput } from "@/components/SearchInput";
import { Section } from "@/components/Section";
import { Skeleton } from "@/components/ui/skeleton";
import { TruncatedText } from "@/components/ui/truncated-text";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import { agentMemoryStorePath } from "@/lib/agents/routes";
import type { AgentOut } from "@/lib/api/agents";
import type { NativeMemoryStore } from "@/lib/api/agentNativeMemory";
import { useAgentNativeMemory } from "@/lib/hooks/useAgentNativeMemory";
import { useProgressiveRows } from "@/components/ui/useProgressiveRows";

/** More stores than this and a project search appears. */
const SEARCH_FROM = 8;

interface Props {
  agent: AgentOut;
}

/** Where the agent writes its memory, for the empty state. */
function memoryLocation(agent: AgentOut): string {
  const dir = abbreviateHomePath(agent.config_dir);
  return agent.type === "codex" ? `${dir}/memories/MEMORY.md` : `${dir}/projects/<project>/memory/`;
}

/** The project a store belongs to: its real directory when Coffer resolved one. */
function projectLabel(store: NativeMemoryStore): string {
  return store.path ? abbreviateHomePath(store.path) : store.project;
}

export function AgentMemoryTab({ agent }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const native = useAgentNativeMemory(agent.uid);
  const agentName = agentTypeLabel(agent.type);
  const [query, setQuery] = useState("");
  // A store with no memory in it (a scratch project the agent once ran in) is
  // not worth a row; with many stores the rest are searched by project or path.
  const all = useMemo(
    () => (native.data?.items ?? []).filter((s) => s.item_count > 0),
    [native.data],
  );
  const stores = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? all.filter((s) => projectLabel(s).toLowerCase().includes(q)) : all;
  }, [all, query]);

  const progressive = useProgressiveRows(stores, { resetKey: query });

  const open = (s: NativeMemoryStore) =>
    navigate(agentMemoryStorePath(agent.type, s.memory_dir, s.path ?? s.project));

  let body: React.ReactNode;
  if (native.error) {
    body = <LoadError error={native.error} onRetry={() => void native.refetch()} />;
  } else if (native.isPending) {
    body = <Skeleton className="h-28 w-full" />;
  } else if (all.length === 0) {
    body = (
      <TabEmpty
        title={t("agents.memoryTab.emptyTitle", { agent: agentName })}
        description={t("agents.memoryTab.emptyBody", {
          agent: agentName,
          path: memoryLocation(agent),
        })}
      />
    );
  } else {
    body = (
      <>
        {all.length > SEARCH_FROM ? (
          <SearchInput
            value={query}
            onChange={setQuery}
            placeholder={t("agents.memoryTab.search")}
            ariaLabel={t("agents.memoryTab.search")}
            className="mb-1 w-64"
          />
        ) : null}
        {stores.length === 0 ? (
          <p className="py-4 text-sm text-text-muted">{t("agents.memoryTab.noMatch")}</p>
        ) : (
          <div className="overflow-hidden rounded-lg border border-border bg-surface-raised">
            <table className="w-full table-fixed border-collapse text-left">
              <thead>
                <tr className="border-b border-border-subtle text-xs font-medium text-text-muted">
                  <th className="w-[34%] px-4 py-2.5 font-medium">
                    {t("agents.memoryTab.cols.project")}
                  </th>
                  <th className="px-2 py-2.5 font-medium">{t("agents.memoryTab.cols.folder")}</th>
                  <th className="w-24 px-2 py-2.5 text-right font-medium">
                    {t("agents.memoryTab.cols.files")}
                  </th>
                  <th className="w-10" aria-hidden />
                </tr>
              </thead>
              <tbody>
                {progressive.visible.map((s) => (
                  <tr
                    // Codex rows share one memory_dir, so key by the routed project too.
                    key={`${s.memory_dir}::${s.path ?? s.project}`}
                    tabIndex={0}
                    onClick={() => open(s)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        open(s);
                      }
                    }}
                    className="cursor-pointer border-b border-border-subtle last:border-b-0 hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring"
                  >
                    <td className="px-4 py-3 align-middle">
                      <TruncatedText
                        text={projectLabel(s)}
                        className="text-sm font-medium text-text"
                      />
                    </td>
                    <td className="px-2 py-3 align-middle">
                      <TruncatedText
                        mono
                        text={abbreviateHomePath(s.memory_dir)}
                        className="text-xs text-text-muted"
                      />
                    </td>
                    <td className="px-2 py-3 text-right align-middle text-xs text-text-muted">
                      {t("agents.memoryTab.files", { count: s.item_count })}
                    </td>
                    <td className="pr-3 align-middle">
                      <ChevronRight className="size-4 text-text-subtle" aria-hidden />
                    </td>
                  </tr>
                ))}
                {progressive.sentinel ? (
                  <tr aria-hidden>
                    <td colSpan={4} className="p-0">
                      {progressive.sentinel}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        )}
      </>
    );
  }

  return (
    <div className="flex max-w-[1000px] flex-col gap-8">
      <Section
        as="h2"
        title={t("agents.memoryTab.own.title", { agent: agentName })}
        gap="tight"
        testId="own-memory-section"
      >
        <p className="mb-1 text-xs text-text-muted">
          {t(
            agent.type === "codex"
              ? "agents.memoryTab.own.descriptionCodex"
              : "agents.memoryTab.own.descriptionClaude",
            { agent: agentName },
          )}
        </p>
        {body}
      </Section>
    </div>
  );
}
