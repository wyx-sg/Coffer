// src/components/agents/overview/OverviewSummary.tsx — "What this agent can use": one row per kind, each opening its tab.
//
// Spec agent-registry (revise-web-ui-ia): one summary row each for Skills, MCP
// servers, Plugins and Hooks, counting Coffer's entries and the agent's own;
// the board adds Memory and Config files. Every number comes from
// useAgentCounts, the same queries the tabs read, so the row and the tab agree.
// While the agent is disabled, MCP servers and Skills read "None while
// disabled" with how many would reach it.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Anchor,
  Brain,
  ChevronRight,
  FileCog,
  Plug,
  Server,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { abbreviateHomePath } from "@/lib/agents/display";
import { agentTabPath, type AgentTab } from "@/lib/agents/routes";
import type { AgentOut, AgentTypeOut } from "@/lib/api/agents";
import { useAgentCounts } from "@/lib/hooks/useAgentCounts";
import { useAgentConfigFiles, useAgentHooks } from "@/lib/hooks/useAgents";
import { toneClass } from "@/lib/statusColors";
import { cn } from "@/lib/utils";

import { Section } from "@/components/Section";
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
  /** No `coffer` entry yet: the MCP row says nothing reaches it until connected. */
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

  const rows: { tab: AgentTab; icon: LucideIcon; summary: SummaryLine | undefined }[] = [
    { tab: "mcp-servers", icon: Server, summary: mcpLine(t, counts.mcp, ctx) },
    { tab: "skills", icon: Sparkles, summary: skillsLine(t, counts.skills, ctx) },
    { tab: "plugins", icon: Plug, summary: pluginsLine(t, counts.plugins) },
    { tab: "hooks", icon: Anchor, summary: hooksLine(t, counts.hooks, ctx) },
    { tab: "memory", icon: Brain, summary: memoryLine(t, counts.memoryStores) },
    { tab: "config", icon: FileCog, summary: configLine(t, configNames) },
  ];

  return (
    <Section title={t(`${K}.heading`)}>
      <ul className="flex flex-col">
        {rows.map(({ tab, icon: Icon, summary }, i) => (
          <li key={tab} className={cn(i > 0 && "border-t border-border-subtle")}>
            <Link
              to={agentTabPath(agent.type, tab)}
              className="flex min-h-[52px] items-center gap-3 rounded-md py-2 text-text hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
            >
              <Icon aria-hidden className="size-4 shrink-0 text-text-muted" />
              <span className="flex min-w-0 grow flex-col gap-0.5">
                <span className="text-sm font-medium">{t(`${K}.title.${tab}`)}</span>
                {summary ? (
                  <span className="break-words text-xs text-text-muted">{summary.line}</span>
                ) : (
                  <Skeleton className="h-3.5 w-48" />
                )}
              </span>
              {summary?.toReview ? (
                <span
                  className={cn(
                    "inline-flex h-5 shrink-0 items-center whitespace-nowrap rounded-xs px-[7px] text-2xs font-medium",
                    toneClass("warn"),
                  )}
                >
                  {t(`${K}.toReview`, { count: summary.toReview })}
                </span>
              ) : null}
              <ChevronRight aria-hidden className="size-3.5 shrink-0 text-text-subtle" />
            </Link>
          </li>
        ))}
      </ul>
    </Section>
  );
}
