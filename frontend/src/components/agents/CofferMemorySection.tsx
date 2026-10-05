// src/components/agents/CofferMemorySection.tsx — the Memory tab's "Coffer's memory" section (board 2.1.49).
//
// Coffer's memory hook (events, file, state), when it last fired, and what it
// delivers, with "Open Memory ›" to the Memory page and Repair — the Review
// changes flow — only when the hook is out of date or missing.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ChevronRight, Wrench } from "lucide-react";

import { ExperimentalTag } from "@/components/ExperimentalTag";
import { Section } from "@/components/Section";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import { cofferEvents, cofferHookState, timeAgo } from "@/lib/agents/hookRows";
import type { AgentOut, CofferHook } from "@/lib/api/agents";
import { useAgentHooks } from "@/lib/hooks/useAgents";

interface Props {
  agent: AgentOut;
  /** Opens the Review changes flow that reinstalls Coffer's hook. Repair shows only when given. */
  onRepair?: () => void;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[172px_minmax(0,1fr)_auto] items-center gap-4 border-t border-border-subtle py-3 text-sm">
      <dt className="font-medium text-text">{label}</dt>
      <dd className="min-w-0 text-text">{children}</dd>
    </div>
  );
}

export function CofferMemorySection({ agent, onRepair }: Props) {
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
