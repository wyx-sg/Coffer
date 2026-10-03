// src/components/agents/overview/OverviewSummary.tsx — "What this agent can use": six tiles, each opening its tab (board 2.1.08).
//
// MCP servers, Skills, Config files, Plugins, Hooks and Memory — a 3×2 grid of
// cards, each a name with its icon and a chevron, the count in big type, one
// fact line and, when something of the agent's own waits for a look, a warning
// "N to review". Every number comes from useAgentCounts, the same queries the
// tabs read, so the tile and the tab agree. While the agent is off, MCP servers
// and Skills read "None while off" with how many would reach it.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Anchor,
  Brain,
  ChevronRight,
  FileCog,
  Plug,
  Server,
  Sparkle,
  type LucideIcon,
} from "lucide-react";

import { Section } from "@/components/Section";
import { StatusWord } from "@/components/status/StatusWord";
import { Skeleton } from "@/components/ui/skeleton";
import { abbreviateHomePath } from "@/lib/agents/display";
import { agentTabPath, type AgentTab } from "@/lib/agents/routes";
import type { AgentOut, AgentTypeOut } from "@/lib/api/agents";
import { useAgentCounts } from "@/lib/hooks/useAgentCounts";
import { useAgentConfigFiles, useAgentHooks } from "@/lib/hooks/useAgents";

import { SectionLine } from "./OverviewParts";
import { baseName, mcpConfigPath } from "./paths";
import {
  configLine,
  hooksLine,
  mcpLine,
  memoryLine,
  pluginsLine,
  skillsLine,
  type SummaryLine,
} from "./summaryLines";

const K = "agents.overviewTab.summary";

interface Props {
  agent: AgentOut;
  typeRow: AgentTypeOut;
  disabled: boolean;
  /** No `coffer` entry yet: the MCP tile says nothing reaches it until connected. */
  notConnected?: boolean;
}

export function OverviewSummary({ agent, typeRow, disabled, notConnected = false }: Props) {
  const { t } = useTranslation();
  const counts = useAgentCounts(agent.uid);
  const hooks = useAgentHooks(agent.uid);
  const configFiles = useAgentConfigFiles(agent.uid);

  const hookPaths = new Set((hooks.data?.items ?? []).map((h) => h.path));
  const ctx = {
    disabled,
    notConnected,
    mcpFile: baseName(mcpConfigPath(agent, typeRow)),
    skillDir: abbreviateHomePath(typeRow.default_skill_dir),
    hookFile: hookPaths.size === 1 ? baseName([...hookPaths][0]) : undefined,
  };
  const configNames = configFiles.data
    ?.filter((f) => f.exists)
    .map((f) => (f.kind === "directory" ? `${f.display_name}/` : f.display_name));

  const tiles: { tab: AgentTab; icon: LucideIcon; summary: SummaryLine | undefined }[] = [
    { tab: "mcp-servers", icon: Server, summary: mcpLine(t, counts.mcp, ctx) },
    { tab: "skills", icon: Sparkle, summary: skillsLine(t, counts.skills, ctx) },
    { tab: "config", icon: FileCog, summary: configLine(t, configNames) },
    { tab: "plugins", icon: Plug, summary: pluginsLine(t, counts.plugins) },
    { tab: "hooks", icon: Anchor, summary: hooksLine(t, counts.hooks, ctx) },
    { tab: "memory", icon: Brain, summary: memoryLine(t, counts.memoryStores) },
  ];

  return (
    <Section title={t(`${K}.heading`)} as="h2">
      <SectionLine>{t(`${K}.description`)}</SectionLine>
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {tiles.map(({ tab, icon: Icon, summary }) => (
          <li key={tab} className="flex">
            <Link
              to={agentTabPath(agent.type, tab)}
              className="flex min-h-[110px] w-full flex-col gap-1.5 rounded-xl border border-border bg-surface-raised px-4 py-3.5 text-text transition-colors hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
            >
              <span className="flex items-center gap-2 text-sm font-medium">
                <Icon aria-hidden className="size-4 shrink-0 text-text-muted" />
                <span className="grow">{t(`${K}.title.${tab}`)}</span>
                <ChevronRight aria-hidden className="size-3.5 shrink-0 text-text-subtle" />
              </span>
              {summary ? (
                <>
                  <span className="text-2xl font-semibold leading-8 tracking-tight">
                    {summary.count}
                  </span>
                  <span className="break-words text-xs text-text-muted">{summary.line}</span>
                  {summary.toReview ? (
                    <StatusWord tone="warn" className="mt-0.5">
                      {t(`${K}.toReview`, { count: summary.toReview })}
                    </StatusWord>
                  ) : null}
                </>
              ) : (
                <Skeleton className="mt-2 h-3.5 w-32" />
              )}
            </Link>
          </li>
        ))}
      </ul>
    </Section>
  );
}
