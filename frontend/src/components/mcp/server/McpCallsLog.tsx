// src/components/mcp/server/McpCallsLog.tsx — one server's calls in the last 24 hours: the Invocations tab (design 4.1.13).
//
// All or Errors · N, an Agent filter, "Last 24 hours"; rows Time · Tool ·
// Called by · Result · Took, newest first. A row opens its call in a 640
// drawer (McpCallDrawer). The invocation log records who called what and how
// it went — never the arguments or the result — and the drawer's footnote says
// so. The pane can own the Errors filter (its banner's "View errors" sets it).
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
import { McpCallDrawer } from "./McpCallDrawer";
import { callTone, seconds, shortTime } from "@/lib/mcp/serverState";

const ALL = "all";

export type CallsFilter = "all" | "errors";

interface Props {
  serverUid: string;
  serverName: string;
  transport: "stdio" | "http" | "unknown";
  agents: readonly AgentOut[];
  /** The built-in `coffer` server, whose calls are read from the cross-server list. */
  builtin?: boolean;
  /** The Errors filter, when the pane owns it. */
  only?: CallsFilter;
  onOnlyChange?: (only: CallsFilter) => void;
  /** View server log, from a stdio call's drawer. */
  onViewLog?: () => void;
}

export function McpCallsLog({
  serverUid,
  serverName,
  transport,
  agents,
  builtin = false,
  only: ownedOnly,
  onOnlyChange,
  onViewLog,
}: Props) {
  const { t } = useTranslation();
  // Fixed at mount: the list shows "the last 24 hours" as of opening it.
  const [since] = useState(() => new Date(Date.now() - 24 * 3600_000).toISOString());
  const calls = useMcpInvocations({ serverUid, limit: 200, since, builtin });
  const [localOnly, setLocalOnly] = useState<CallsFilter>("all");
  const only = ownedOnly ?? localOnly;
  const setOnly = onOnlyChange ?? setLocalOnly;
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
  const open = rows.find((r) => r.id === openId) ?? null;

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
          <SelectTrigger className="w-36" aria-label={t("mcp.page.log.agent")}>
            <SelectValue>{agent === ALL ? t("mcp.page.log.agent") : nameOf(agent)}</SelectValue>
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
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setOpenId(r.id);
                      }
                    }}
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
                          r.status === "ok" ? "text-text-muted" : "text-danger",
                        )}
                      >
                        {r.status === "ok" ? null : <StatusDot tone={callTone(r.status)} />}
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
      <McpCallDrawer
        call={open}
        agentName={open ? nameOf(open.agent_uid) : ""}
        serverName={serverName}
        transport={transport}
        onClose={() => setOpenId(null)}
        onViewLog={() => {
          setOpenId(null);
          onViewLog?.();
        }}
      />
    </div>
  );
}
