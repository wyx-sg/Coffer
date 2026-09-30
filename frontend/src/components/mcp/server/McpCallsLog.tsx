// src/components/mcp/server/McpCallsLog.tsx — one server's calls in the last 24 hours: the drawer's Calls tab and the Invocations tab (design 4.1.09, 4.1.22, 4.1.28).
//
// All or Errors · N, one agent or all, "Last 24 hours"; rows Time · Tool ·
// Called by · Result · Took, newest first, the chosen one (the newest by
// default) opened below with its result, duration and session. The
// invocation log records who called what and how it went — never the
// arguments or the result — and the footnote says so.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { StatusDot } from "@/components/status/StatusDot";
import { Segmented } from "@/components/ui/segmented";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import type { AgentOut } from "@/lib/api/agents";
import { useMcpInvocations } from "@/lib/hooks/useMcpInvocations";
import { cn } from "@/lib/utils";
import { McpCallDetail } from "./McpCallDetail";
import { callTone, seconds, shortTime } from "./serverState";

const ALL = "all";

interface Props {
  serverUid: string;
  agents: readonly AgentOut[];
  /** The built-in `coffer` server, whose calls are read from the cross-server list. */
  builtin?: boolean;
}

export function McpCallsLog({ serverUid, agents, builtin = false }: Props) {
  const { t } = useTranslation();
  // Fixed at mount: the list shows "the last 24 hours" as of opening it.
  const [since] = useState(() => new Date(Date.now() - 24 * 3600_000).toISOString());
  const calls = useMcpInvocations({ serverUid, limit: 200, since, builtin });
  const [only, setOnly] = useState<"all" | "errors">("all");
  const [agent, setAgent] = useState<string>(ALL);
  const [openId, setOpenId] = useState<number | null>(null);

  const all = useMemo(() => calls.data?.invocations ?? [], [calls.data]);
  const rows = useMemo(
    () =>
      all.filter(
        (r) => (only === "all" || r.status !== "ok") && (agent === ALL || r.agent_uid === agent),
      ),
    [all, only, agent],
  );
  const errors = all.filter((r) => r.status !== "ok").length;
  const agentOf = (uid: string | null) => agents.find((a) => a.uid === uid);
  const nameOf = (uid: string | null) => agentOf(uid)?.display_name ?? t("mcp.page.unknownSession");
  const open = rows.find((r) => r.id === openId) ?? rows[0] ?? null;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Segmented
          label={t("mcp.page.log.show")}
          value={only}
          onChange={setOnly}
          options={[
            { value: "all", label: t("mcp.page.log.all") },
            { value: "errors", label: t("mcp.page.log.errors", { count: errors }) },
          ]}
        />
        <Select value={agent} onValueChange={setAgent}>
          <SelectTrigger className="w-40" aria-label={t("mcp.page.log.agent")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t("agentBadge.allAgents")}</SelectItem>
            {agents.map((a) => (
              <SelectItem key={a.uid} value={a.uid}>
                {a.display_name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="ml-auto text-xs text-text-muted">{t("mcp.page.last24h")}</span>
      </div>
      {calls.isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : rows.length === 0 ? (
        <p className="text-xs text-text-muted">{t("mcp.page.noCalls")}</p>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <table className="w-full text-xs" aria-label={t("mcp.page.log.calls")}>
            <thead>
              <tr className="border-b border-border-subtle text-left text-2xs font-semibold text-text-muted">
                <th className="px-2 py-1.5 font-semibold">{t("mcp.page.log.time")}</th>
                <th className="py-1.5 font-semibold">{t("mcp.page.log.tool")}</th>
                <th className="py-1.5 font-semibold">{t("mcp.page.calledBy")}</th>
                <th className="py-1.5 font-semibold">{t("mcp.page.log.result")}</th>
                <th className="px-2 py-1.5 text-right font-semibold">{t("mcp.page.log.took")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const a = agentOf(r.agent_uid);
                return (
                  <tr
                    key={r.id}
                    aria-selected={r.id === open?.id}
                    className={cn(
                      "cursor-pointer border-b border-border-subtle hover:bg-surface-hover",
                      r.id === open?.id && "bg-surface-selected",
                    )}
                    onClick={() => setOpenId(r.id)}
                  >
                    <td className="px-2 py-2 tabular-nums">{shortTime(r.timestamp)}</td>
                    <td className="py-2 font-mono">{r.capability_key}</td>
                    <td className="py-2">
                      {a ? (
                        <AgentBadge type={a.type} name={a.display_name} showName size="sm" />
                      ) : (
                        <span className="text-text-muted">{t("mcp.page.unknownSession")}</span>
                      )}
                    </td>
                    <td className="py-2">
                      <span
                        className={cn(
                          "inline-flex items-center gap-1.5",
                          r.status === "ok" ? "text-text" : "text-danger",
                        )}
                      >
                        <StatusDot tone={callTone(r.status)} />
                        {t(`mcp.page.log.status.${r.status}`)}
                      </span>
                    </td>
                    <td className="px-2 py-2 text-right tabular-nums">{seconds(r.duration_ms)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {open ? <McpCallDetail call={open} agentName={nameOf(open.agent_uid)} /> : null}
      {!open ? <p className="text-xs text-text-muted">{t("mcp.page.log.callsFootnote")}</p> : null}
    </div>
  );
}
