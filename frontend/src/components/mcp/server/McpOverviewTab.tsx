// src/components/mcp/server/McpOverviewTab.tsx — the open server's Overview (design 4.1.04–4.1.09): stacked, banner → Last 24 hours → Requires → Most-called tools.
//
// The state's banner first (handed in; it holds the fix for its problem), then
// the last 24 hours — calls and errors, and per calling agent its calls,
// errors and last call, with View in Activity; an Off server says only when it
// was last called and by whom. Then what it requires of this Mac, and its
// most-called tools, read-only (the switches are on the Tools tab).
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Section, SectionStack } from "@/components/Section";
import { AgentBadge } from "@/components/agent/AgentBadge";
import { Skeleton } from "@/components/ui/skeleton";
import type { AgentOut } from "@/lib/api/agents";
import type { InvocationSummary } from "@/lib/hooks/useMcpServerPage";
import type { McpStatusDetail } from "@/lib/hooks/useMcpServerStatus";
import { cn } from "@/lib/utils";
import { relativeTime, shortDate, type ServerState } from "@/lib/mcp/serverState";
import { McpRequires } from "./McpRequires";

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
  name: string;
  /** Off servers link nowhere and say only their last call. */
  enabled: boolean;
  state: ServerState;
  agents: readonly AgentOut[];
  summary: InvocationSummary | undefined;
  summaryPending: boolean;
  /** What the server requires of this Mac; empty for the built-in one. */
  requires?: McpStatusDetail["requires"];
  /** The state's banner ("why, and what next"). */
  callout?: ReactNode;
  /** The most-called tools; the Tools tab has the rest. */
  tools: ReactNode;
  /** The built-in server's one-line description of the 24-hour block. */
  builtin?: boolean;
  /** The Activity page on this server's calls, where "View in Activity" goes. */
  activityHref: string;
}

export function McpOverviewTab({
  name,
  enabled,
  state,
  agents,
  summary,
  summaryPending,
  requires = [],
  callout,
  tools,
  builtin = false,
  activityHref,
}: Props) {
  const { t } = useTranslation();
  const agentOf = (uid: string | null | undefined) => agents.find((a) => a.uid === uid);

  const note =
    summary && summary.calls > 0 && state.kind === "secretMissing"
      ? t("mcp.page.stoppedAtCoffer")
      : state.kind === "launcherMissing"
        ? t("mcp.page.noCallsWhileLauncherMissing")
        : summary && summary.by_agent.length === 0
          ? t("mcp.page.noCalls")
          : null;

  // An Off server's block: when it was last called, and by whom.
  const lastCall = summary?.by_agent
    .filter((row) => row.last_call_at)
    .sort((a, b) => (b.last_call_at ?? "").localeCompare(a.last_call_at ?? ""))[0];
  const offNote = lastCall?.last_call_at
    ? t("mcp.page.offLastCall", {
        at: shortDate(lastCall.last_call_at),
        agent: agentOf(lastCall.agent_uid)?.display_name ?? t("mcp.page.unknownSession"),
      })
    : t("mcp.page.offNoCalls");

  return (
    <div className="flex flex-col gap-6">
      {callout}
      <SectionStack>
        <Section
          title={t("mcp.page.last24h")}
          gap="snug"
          labelled
          compact
          actions={
            enabled ? (
              <Link
                to={activityHref}
                className="text-xs font-label text-accent-text hover:underline"
              >
                {t("mcp.page.viewInActivity")}
              </Link>
            ) : null
          }
        >
          <p className="-mt-1 text-xs text-text-muted">
            {t(builtin ? "mcp.page.last24hSubBuiltin" : "mcp.page.last24hSub", { name })}
          </p>
          {summaryPending ? (
            <Skeleton className="h-24 w-full" />
          ) : !enabled ? (
            <p className="text-xs text-text-muted" data-testid="mcp-24h-off">
              {offNote}
            </p>
          ) : summary ? (
            <>
              <p className="flex gap-10 pb-1" data-testid="mcp-24h-totals">
                <Big value={summary.calls} label={t("mcp.page.calls", { count: summary.calls })} />
                <Big
                  value={summary.errors}
                  label={t("mcp.page.errors", { count: summary.errors })}
                  danger
                />
              </p>
              <table className="w-full text-sm" aria-label={t("mcp.page.calledBy")}>
                <thead>
                  <tr className="h-[26px] border-t border-border-subtle text-left text-2xs font-semibold text-text-subtle">
                    <th className="font-semibold">{t("mcp.page.calledBy")}</th>
                    <th className="w-14 text-right font-semibold">{t("mcp.page.colCalls")}</th>
                    <th className="w-14 text-right font-semibold">{t("mcp.page.colErrors")}</th>
                    <th className="w-24 text-right font-semibold">{t("mcp.page.colLastCall")}</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.by_agent.map((row) => {
                    const agent = agentOf(row.agent_uid);
                    return (
                      <tr
                        key={row.agent_uid ?? "none"}
                        className="h-8 border-t border-border-subtle"
                      >
                        <td>
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
                        <td className="text-right text-xs tabular-nums">{row.calls}</td>
                        <td
                          className={cn(
                            "text-right text-xs tabular-nums",
                            row.errors > 0 && "text-danger",
                          )}
                        >
                          {row.errors}
                        </td>
                        <td className="text-right text-xs text-text-muted">
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
        <McpRequires requires={requires} />
        {tools}
      </SectionStack>
    </div>
  );
}
