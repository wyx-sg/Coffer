// frontend/src/components/agents/AgentMemoryTab.tsx — spec agent-registry
// "Read one native memory store's files read-only".
// The agent detail page's Memory tab (boards 2.1.49–50). Two sections:
//
// 1. Coffer's memory (Experimental; only with the memory feature on): Coffer's
//    memory hook (events, file, state), when it last fired, and what it
//    delivers, with "Open Memory ›" to the Memory page and Repair — the Review
//    changes flow — only when the hook is out of date or missing.
// 2. The agent's own memory: its native stores (Claude Code's
//    ~/.claude/projects/<project>/memory/, Codex's ~/.codex/memories/MEMORY.md
//    sliced by project), read-only, one bordered list. A store is a directory,
//    so a row opens its own page (a file tree and a read-only preview). Coffer
//    reads them to build shared memory and never writes them.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { ChevronRight, Wrench } from "lucide-react";

import { TabEmpty } from "./tabs/TabEmpty";
import { ExperimentalTag } from "@/components/ExperimentalTag";
import { LoadError } from "@/components/LoadError";
import { SearchInput } from "@/components/SearchInput";
import { Section } from "@/components/Section";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import { cofferEvents, cofferHookState, timeAgo } from "@/lib/agents/hookRows";
import { agentMemoryStorePath } from "@/lib/agents/routes";
import type { AgentOut, CofferHook } from "@/lib/api/agents";
import type { NativeMemoryStore } from "@/lib/api/agentNativeMemory";
import { useAgentNativeMemory } from "@/lib/hooks/useAgentNativeMemory";
import { useAgentHooks } from "@/lib/hooks/useAgents";
import { useFeatureEnabled } from "@/lib/hooks/useFeatures";

/** More stores than this and a project search appears. */
const SEARCH_FROM = 8;

interface Props {
  agent: AgentOut;
  /** Opens the Review changes flow that reinstalls Coffer's hook. Repair shows only when given. */
  onRepair?: () => void;
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

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[172px_minmax(0,1fr)_auto] items-center gap-4 border-t border-border-subtle py-3 text-sm">
      <dt className="font-medium text-text">{label}</dt>
      <dd className="min-w-0 text-text">{children}</dd>
    </div>
  );
}

function CofferMemorySection({ agent, onRepair }: Props) {
  const { t, i18n } = useTranslation();
  const hooks = useAgentHooks(agent.uid);
  const hook: CofferHook | null = hooks.data?.coffer_hook ?? null;
  const agentName = agentTypeLabel(agent.type);
  const state = hook ? cofferHookState(hook) : null;
  const events = hook ? cofferEvents(hook) : [];

  return (
    <Section
      as="h2"
      title={t("agents.memoryTab.coffer.title")}
      aside={<ExperimentalTag />}
      actions={
        <>
          {state?.repair && onRepair ? (
            <Button size="sm" onClick={onRepair}>
              <Wrench aria-hidden /> {t("agents.memoryTab.coffer.repair")}
            </Button>
          ) : null}
          <Link
            to="/memory"
            className="inline-flex items-center gap-0.5 text-xs font-medium text-accent-text hover:underline"
          >
            {t("agents.memoryTab.coffer.open")}
            <ChevronRight className="size-3.5" aria-hidden />
          </Link>
        </>
      }
      gap="tight"
      testId="coffer-memory-section"
    >
      <p className="mb-1 text-xs text-text-muted">
        {t("agents.memoryTab.coffer.description", { agent: agentName })}
      </p>
      <dl className="flex flex-col">
        <div className="grid grid-cols-[172px_minmax(0,1fr)_auto] items-center gap-4 border-t border-border-subtle py-3 text-sm">
          <dt className="font-medium text-text">{t("agents.memoryTab.coffer.hook")}</dt>
          <dd className="min-w-0 text-text">
            {hook ? (
              <>
                {events.length === 1
                  ? t("agents.memoryTab.coffer.oneEventIn", { event: events[0] })
                  : t("agents.memoryTab.coffer.eventsIn", { count: events.length })}{" "}
                <span className="break-all font-mono text-xs">{abbreviateHomePath(hook.path)}</span>
              </>
            ) : hooks.isPending ? (
              <Skeleton className="h-4 w-48" />
            ) : (
              "—"
            )}
          </dd>
          {state ? (
            <dd>
              <StatusWord tone={state.tone}>{t(`agents.hooks.state.${state.word}`)}</StatusWord>
            </dd>
          ) : null}
        </div>
        <Row label={t("agents.memoryTab.coffer.lastFired")}>
          <span className="text-text-muted">
            {hook?.last_fired_at
              ? timeAgo(hook.last_fired_at, i18n.language)
              : t("agents.memoryTab.coffer.never")}
          </span>
        </Row>
        <Row label={t("agents.memoryTab.coffer.delivers")}>
          <span className="text-text-muted">
            {t("agents.memoryTab.coffer.deliversBody", { agent: agentName })}
          </span>
        </Row>
      </dl>
    </Section>
  );
}

export function AgentMemoryTab({ agent, onRepair }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const memoryOn = useFeatureEnabled("memory") === true;
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
          <ul className="overflow-hidden rounded-lg border border-border bg-surface-raised">
            {stores.map((s) => (
              <li
                // Codex rows share one memory_dir, so key by the routed project too.
                key={`${s.memory_dir}::${s.path ?? s.project}`}
                className="border-b border-border-subtle last:border-b-0"
              >
                <button
                  type="button"
                  onClick={() => open(s)}
                  className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring"
                >
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="truncate text-sm font-medium text-text">
                      {projectLabel(s)}
                    </span>
                    <span className="truncate font-mono text-xs text-text-muted">
                      {abbreviateHomePath(s.memory_dir)}
                    </span>
                  </span>
                  <span className="shrink-0 text-xs text-text-muted">
                    {t("agents.memoryTab.files", { count: s.item_count })}
                  </span>
                  <ChevronRight className="size-4 shrink-0 text-text-subtle" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        )}
      </>
    );
  }

  return (
    <div className="flex max-w-[760px] flex-col gap-8">
      {memoryOn ? <CofferMemorySection agent={agent} onRepair={onRepair} /> : null}
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
