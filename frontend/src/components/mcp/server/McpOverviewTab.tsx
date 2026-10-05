// src/components/mcp/server/McpOverviewTab.tsx — the open server's Overview (design 4.1.04–4.1.09): stacked, banner → Last 24 hours → Requires → Most-called tools.
//
// The state's banner first (handed in; it holds the fix for its problem), then
// the last 24 hours (McpLast24h) — calls and errors, and per calling agent its
// calls, errors and last call, with View in Activity; an Off server says only
// when it was last called and by whom. Then what it requires of this Mac, and
// its most-called tools, read-only (the switches are on the Tools tab).
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { SectionStack } from "@/components/Section";
import type { AgentOut } from "@/lib/api/agents";
import type { InvocationSummary } from "@/lib/hooks/useMcpServerPage";
import type { McpStatusDetail } from "@/lib/hooks/useMcpServerStatus";
import type { ServerState } from "@/lib/mcp/serverState";
import { McpLast24h } from "./McpLast24h";
import { McpRequires } from "./McpRequires";

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
  /** Replace key… on a Requires secret row: point that env var / header at another secret. */
  onRebindSecret?: (field: string, ref: string) => Promise<unknown>;
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
  onRebindSecret,
  callout,
  tools,
  builtin = false,
  activityHref,
}: Props) {
  const { t } = useTranslation();
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
        <McpLast24h
          name={name}
          enabled={enabled}
          agents={agents}
          summary={summary}
          summaryPending={summaryPending}
          activityHref={activityHref}
          note={note}
          builtin={builtin}
        />
        <McpRequires
          requires={requires}
          onRebind={onRebindSecret ? (r, ref) => onRebindSecret(r.name, ref) : undefined}
        />
        {tools}
      </SectionStack>
    </div>
  );
}
