// src/components/mcp/server/McpOverviewTab.tsx — the open server's Overview (design 4.1.02–4.1.06): why and what next, who it reaches, its last 24 hours, its busiest tools.
//
// The state's callout first (handed in), a missing secret's facts under it,
// then two columns: Agents — whether its tools are listed to agents directly
// or mostly behind `coffer__search_tools`, and that reach is set on this Mac
// only (the reach itself is the header's button); Last 24 hours — calls and
// errors, and per calling agent its calls, errors and last call, with Open in
// Activity. Then its most-called tools.
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Section, SectionStack } from "@/components/Section";
import { AgentBadge } from "@/components/agent/AgentBadge";
import { Skeleton } from "@/components/ui/skeleton";
import type { AgentOut } from "@/lib/api/agents";
import type { InvocationSummary, ToolTiering } from "@/lib/hooks/useMcpServerPage";
import { cn } from "@/lib/utils";
import { relativeTime, type ServerState } from "@/lib/mcp/serverState";

export function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-3 border-b border-border-subtle py-2.5 text-sm last:border-b-0">
      <dt className="w-36 shrink-0 text-xs text-text-muted">{label}</dt>
      <dd className="min-w-0 text-text">{children}</dd>
    </div>
  );
}

function Big({ value, label, danger }: { value: number; label: string; danger?: boolean }) {
  return (
    <span className="flex flex-col">
      <span
        className={cn(
          "text-xl font-semibold tabular-nums",
          danger && value > 0 ? "text-danger" : "text-text",
        )}
      >
        {value.toLocaleString()}
      </span>{" "}
      <span className="text-xs text-text-muted">{label}</span>
    </span>
  );
}

interface Props {
  /** Off servers link nowhere and reach no agent. */
  enabled: boolean;
  state: ServerState;
  agents: readonly AgentOut[];
  tiering: ToolTiering | null | undefined;
  summary: InvocationSummary | undefined;
  summaryPending: boolean;
  /** The state's callout ("why, and what next"). */
  callout: ReactNode;
  /** Blocks between the callout and the two columns (a missing secret's facts). */
  facts?: ReactNode;
  /** The most-called tools; the Tools tab has the rest. */
  tools: ReactNode;
  /** Rows for the Agents column in place of the reach and storage facts
   *  (the built-in server's status). */
  agentFacts?: ReactNode;
}

export function McpOverviewTab({
  enabled,
  state,
  agents,
  tiering,
  summary,
  summaryPending,
  callout,
  facts,
  tools,
  agentFacts,
}: Props) {
  const { t } = useTranslation();
  const agentOf = (uid: string | null | undefined) => agents.find((a) => a.uid === uid);

  let reachesAgents: ReactNode;
  if (!enabled) reachesAgents = "—";
  else if (!tiering || !tiering.enabled || tiering.behind_search.length === 0)
    reachesAgents = t("mcp.page.listedDirectly");
  else
    reachesAgents = (
      <span className="flex flex-wrap items-baseline gap-x-3">
        <span>{t("mcp.page.mostBehindSearchValue")}</span>
        <span className="text-xs text-text-muted">
          {t("mcp.page.listedAndBehind", {
            listed: tiering.listed.length,
            behind: tiering.behind_search.length,
          })}
        </span>
      </span>
    );

  const note =
    summary && summary.calls > 0 && state.kind === "secretMissing"
      ? t("mcp.page.stoppedAtCoffer")
      : state.kind === "launcherMissing"
        ? t("mcp.page.noCallsWhileLauncherMissing")
        : summary && summary.by_agent.length === 0
          ? t("mcp.page.noCalls")
          : null;

  return (
    <div className="flex flex-col gap-6">
      {callout}
      <SectionStack>
        {facts}
        <Section title={t("mcp.page.agents")} gap="tight" labelled>
          <dl className="flex flex-col">
            <Fact label={t("mcp.page.toolsReachAgents")}>{reachesAgents}</Fact>
            {agentFacts ?? (
              <Fact label={t("mcp.page.stored")}>
                <span className="text-xs">{t("mcp.page.storedValue")}</span>
              </Fact>
            )}
          </dl>
        </Section>

        <Section
          title={t("mcp.page.last24h")}
          gap="snug"
          labelled
          actions={
            enabled ? (
              <Link to="/activity?tab=mcp" className="text-xs text-accent hover:underline">
                {t("mcp.page.openInActivity")}
              </Link>
            ) : null
          }
        >
          {summaryPending ? (
            <Skeleton className="h-24 w-full" />
          ) : summary ? (
            <>
              <p className="flex gap-10" data-testid="mcp-24h-totals">
                <Big value={summary.calls} label={t("mcp.page.calls", { count: summary.calls })} />
                <Big
                  value={summary.errors}
                  label={t("mcp.page.errors", { count: summary.errors })}
                  danger
                />
              </p>
              <table className="w-full text-sm" aria-label={t("mcp.page.calledBy")}>
                <thead>
                  <tr className="border-b border-border-subtle text-left text-2xs font-semibold text-text-muted">
                    <th className="py-1.5 font-semibold">{t("mcp.page.calledBy")}</th>
                    <th className="py-1.5 text-right font-semibold">{t("mcp.page.colCalls")}</th>
                    <th className="py-1.5 text-right font-semibold">{t("mcp.page.colErrors")}</th>
                    <th className="py-1.5 text-right font-semibold">{t("mcp.page.colLastCall")}</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.by_agent.map((row) => {
                    const agent = agentOf(row.agent_uid);
                    return (
                      <tr key={row.agent_uid ?? "none"} className="border-b border-border-subtle">
                        <td className="py-2">
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
                        <td className="py-2 text-right tabular-nums">{row.calls}</td>
                        <td
                          className={cn(
                            "py-2 text-right tabular-nums",
                            row.errors > 0 && "text-danger",
                          )}
                        >
                          {row.errors}
                        </td>
                        <td className="py-2 text-right text-xs text-text-muted">
                          {row.last_call_at ? relativeTime(row.last_call_at) : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {note ? <p className="text-xs text-text-muted">{note}</p> : null}
            </>
          ) : (
            <p className="text-xs text-text-muted">{t("mcp.page.summaryUnavailable")}</p>
          )}
        </Section>
        {tools}
      </SectionStack>
    </div>
  );
}
