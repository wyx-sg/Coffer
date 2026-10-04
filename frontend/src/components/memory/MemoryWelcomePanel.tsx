// frontend/src/components/memory/MemoryWelcomePanel.tsx — the first-run state of /memory.
//
// Two shapes (designs 5.2.10 and 5.2.11). With agents connected: "Nothing
// distilled yet", the one next step Update memory, and "Found on this Mac" —
// each connected agent with where its own memory lives and how much of it
// there is, so the reader sees what Update memory will read. With no agent
// connected there is nothing to read at all, so the one step is connecting an
// agent. Nothing here is user-created: Coffer distils what the agents already
// learned out of their own memory and never writes back to it.
import { Bot, Brain } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { sortAgents } from "@/components/agent/agentOrder";
import { EmptyState } from "@/components/EmptyState";
import { MemoryUpdateButton } from "@/components/memory/MemoryUpdateButton";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { abbreviateHomePath } from "@/lib/agents/display";
import { useAgents } from "@/lib/hooks/useAgents";
import { useAgentNativeMemory } from "@/lib/hooks/useAgentNativeMemory";
import { Section } from "@/components/Section";

type AgentRow = NonNullable<ReturnType<typeof useAgents>["data"]>[number];

function FoundRow({ agent }: { agent: AgentRow }) {
  const { t } = useTranslation();
  const stores = useAgentNativeMemory(agent.uid);
  const items = stores.data?.items ?? [];
  const files = items.reduce((sum, s) => sum + s.item_count, 0);
  return (
    <li className="flex min-h-[52px] items-center gap-2.5 border-t border-border-subtle px-3.5 first:border-t-0">
      <AgentBadge type={agent.type} name={agent.name} size="sm" tooltip={false} />
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="text-sm text-text">{agent.display_name || agent.name}</span>
        <span className="truncate font-mono text-2xs text-text-muted">
          {abbreviateHomePath(agent.config_dir)}
        </span>
      </div>
      <span className="ml-auto text-xs text-text">
        {stores.isPending ? (
          <Skeleton className="h-4 w-24" />
        ) : items.length === 0 ? (
          t("memory.welcome.foundNone")
        ) : (
          t("memory.welcome.foundCount", {
            count: files,
            projects: t("memory.welcome.projects", { count: items.length }),
          })
        )}
      </span>
    </li>
  );
}

export function MemoryWelcomePanel() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const agents = useAgents();

  if (agents.isPending) return <Skeleton className="h-60 w-full" />;
  const connected = sortAgents(agents.data ?? []);

  if (connected.length === 0) {
    return (
      <EmptyState
        icon={Bot}
        title={t("memory.welcome.noAgentsTitle")}
        description={t("memory.welcome.noAgentsBody")}
        action={
          <Button type="button" onClick={() => navigate("/agents")}>
            {t("memory.welcome.connect")}
          </Button>
        }
      />
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-[560px] flex-col gap-1.5">
      <EmptyState
        icon={Brain}
        title={t("memory.welcome.title")}
        description={t("memory.welcome.body")}
        action={<MemoryUpdateButton />}
      />
      <Section
        as="h2"
        gap="snug"
        labelled
        title={t("memory.welcome.found")}
        aside={<span className="text-xs text-text-muted">{t("memory.welcome.foundMeta")}</span>}
      >
        <ul
          className="overflow-hidden rounded-lg border border-border-subtle bg-surface-raised"
          data-testid="memory-found"
        >
          {connected.map((a) => (
            <FoundRow key={a.uid} agent={a} />
          ))}
        </ul>
      </Section>
    </div>
  );
}
