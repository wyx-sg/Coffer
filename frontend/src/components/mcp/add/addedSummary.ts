// frontend/src/components/mcp/add/addedSummary.ts — how the Add dialog words
// what it just registered: who can call a server ("all agents", the chosen
// agents' names) and the one-line "stdio · npx" of how it runs. Pure; words come
// from `t`.
import type { TFunction } from "i18next";

import { agentTypeLabel } from "@/lib/agents/display";
import type { ImportReport, NewServer, ReachIntent } from "@/lib/mcp/importMcpServers";
import type { AddedServer } from "./ApprovalStep";

interface AgentLike {
  uid: string;
  name: string;
  type?: string | null;
}

/** "all agents", "no agent yet", or the chosen agents' names. */
export function reachPhrase(
  t: TFunction,
  reach: ReachIntent,
  agents: readonly AgentLike[] | undefined,
): string {
  if (reach.mode === "everywhere") return t("mcp.add.reachAll");
  if (reach.mode === "disabled") return t("mcp.add.reachOff");
  const names = reach.agents.map((uid) => {
    const a = agents?.find((x) => x.uid === uid);
    return a ? agentTypeLabel(a.type ?? a.name) : uid;
  });
  return names.length > 0 ? names.join(", ") : t("mcp.add.reachOff");
}

/** "stdio · npx" / "Streamable HTTP". */
function summaryOf(t: TFunction, s: Pick<NewServer, "transportType" | "command">): string {
  if (s.transportType === "http") return t("mcp.add.summaryHttp");
  return t("mcp.add.summaryStdio", { program: s.command.split(/[\\/]/).pop() ?? s.command });
}

/** What the approval step lists: every server just added, with its waiting secrets. */
export function addedList(
  t: TFunction,
  batch: NewServer[],
  report: ImportReport,
  reach: ReachIntent,
  agents: readonly AgentLike[] | undefined,
): AddedServer[] {
  return report.created.map((c) => {
    const srv = batch.find((b) => b.name === c.name);
    return {
      name: c.name,
      summary: srv ? summaryOf(t, srv) : "",
      reach: reachPhrase(t, reach, agents),
      waiting: report.awaitingApproval.find((w) => w.name === c.name)?.secrets ?? [],
    };
  });
}
