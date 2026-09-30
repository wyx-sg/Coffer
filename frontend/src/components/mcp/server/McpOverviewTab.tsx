// src/components/mcp/server/McpOverviewTab.tsx — the open server's Overview (design 4.1.02): who it reaches, its last 24 hours, its busiest tools.
//
// Agents — who it is available to (the reach itself is the header's button),
// whether its tools are listed to agents directly or mostly behind
// `coffer__search_tools`, and that reach is set on this Mac only. Last 24
// hours — calls and errors, and per calling agent its calls, errors and last
// call, with Open in Activity. Then its first few tools, busiest first, with
// "Show N more" opening the Tools tab.
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { Skeleton } from "@/components/ui/skeleton";
import type { AgentOut } from "@/lib/api/agents";
import type { ResourceOut } from "@/lib/api/resources";
import type { InvocationSummary, ToolTiering } from "@/lib/hooks/useMcpServerPage";
import { reachWords } from "./reachWords";
import { shortTime } from "./serverState";

function Block({
  title,
  aside,
  children,
}: {
  title: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold text-text">{title}</h3>
        {aside ? <span className="ml-auto">{aside}</span> : null}
      </div>
      {children}
    </section>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-3 text-sm">
      <dt className="w-36 shrink-0 text-text-muted">{label}</dt>
      <dd className="min-w-0 text-text">{children}</dd>
    </div>
  );
}

interface Props {
  resource: ResourceOut;
  agents: readonly AgentOut[];
  tiering: ToolTiering | null | undefined;
  summary: InvocationSummary | undefined;
  summaryPending: boolean;
  /** The top of the tools list; the Tools tab has the rest. */
  tools: ReactNode;
}

export function McpOverviewTab({
  resource,
  agents,
  tiering,
  summary,
  summaryPending,
  tools,
}: Props) {
  const { t } = useTranslation();
  const agentOf = (uid: string | null | undefined) => agents.find((a) => a.uid === uid);

  let reachesAgents: string;
  if (!resource.enabled) reachesAgents = "—";
  else if (!tiering || !tiering.enabled || tiering.behind_search.length === 0)
    reachesAgents = t("mcp.page.listedDirectly");
  else
    reachesAgents = t("mcp.page.mostlyBehindSearch", {
      listed: tiering.listed.length,
      behind: tiering.behind_search.length,
    });

  return (
    <div className="flex flex-col gap-7">
      <Block title={t("mcp.page.agents")}>
        <dl className="flex flex-col gap-1.5">
          <Fact label={t("mcp.page.availableTo")}>{reachWords(t, resource, agents)}</Fact>
          <Fact label={t("mcp.page.toolsReachAgents")}>{reachesAgents}</Fact>
          <Fact label={t("mcp.page.stored")}>{t("mcp.page.storedValue")}</Fact>
        </dl>
      </Block>

      <Block
        title={t("mcp.page.last24h")}
        aside={
          <Link to="/activity?tab=mcp" className="text-xs text-accent hover:underline">
            {t("mcp.page.openInActivity")}
          </Link>
        }
      >
        {summaryPending ? (
          <Skeleton className="h-16 w-full" />
        ) : summary ? (
          <>
            <p
              className="flex items-baseline gap-4 text-sm text-text-muted"
              data-testid="mcp-24h-totals"
            >
              <span>
                <span className="text-lg font-semibold text-text">
                  {summary.calls.toLocaleString()}
                </span>{" "}
                {t("mcp.page.calls", { count: summary.calls })}
              </span>
              <span>
                <span className="text-lg font-semibold text-text">
                  {summary.errors.toLocaleString()}
                </span>{" "}
                {t("mcp.page.errors", { count: summary.errors })}
              </span>
            </p>
            {summary.by_agent.length > 0 ? (
              <table className="w-full text-sm" aria-label={t("mcp.page.calledBy")}>
                <thead>
                  <tr className="text-left text-xs text-text-muted">
                    <th className="py-1 font-medium">{t("mcp.page.calledBy")}</th>
                    <th className="py-1 text-right font-medium">{t("mcp.page.colCalls")}</th>
                    <th className="py-1 text-right font-medium">{t("mcp.page.colErrors")}</th>
                    <th className="py-1 text-right font-medium">{t("mcp.page.colLastCall")}</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.by_agent.map((row) => {
                    const agent = agentOf(row.agent_uid);
                    return (
                      <tr key={row.agent_uid ?? "none"} className="border-t border-border-subtle">
                        <td className="py-1.5">
                          {agent ? (
                            <AgentBadge
                              type={agent.type}
                              name={agent.display_name}
                              showName
                              size="sm"
                            />
                          ) : (
                            <span className="text-text-muted">{t("mcp.page.unknownSession")}</span>
                          )}
                        </td>
                        <td className="py-1.5 text-right tabular-nums">{row.calls}</td>
                        <td className="py-1.5 text-right tabular-nums">{row.errors}</td>
                        <td className="py-1.5 text-right text-text-muted">
                          {row.last_call_at ? shortTime(row.last_call_at) : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <p className="text-xs text-text-muted">{t("mcp.page.noCalls")}</p>
            )}
          </>
        ) : (
          <p className="text-xs text-text-muted">{t("mcp.page.summaryUnavailable")}</p>
        )}
      </Block>

      <Block title={t("mcp.server.tabs.tools")}>{tools}</Block>
    </div>
  );
}
