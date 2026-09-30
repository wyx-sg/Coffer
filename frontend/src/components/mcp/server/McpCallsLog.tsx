// src/components/mcp/server/McpCallsLog.tsx — the drawer's Calls tab: this server's calls in the last 24 hours (design 4.1.09).
//
// All or Errors, one agent or all; rows Time · Tool · Called by · Result ·
// Took, newest first; a chosen row's result, duration and session below. The
// invocation log records who called what and how it went — never the
// arguments or the result — and the footnote says so.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import type { AgentOut } from "@/lib/api/agents";
import { useMcpInvocations } from "@/lib/hooks/useMcpInvocations";
import { cn } from "@/lib/utils";
import { shortTime } from "./serverState";

interface Props {
  serverUid: string;
  agents: readonly AgentOut[];
}

function took(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`;
}

export function McpCallsLog({ serverUid, agents }: Props) {
  const { t } = useTranslation();
  // Fixed at mount: the drawer shows "the last 24 hours" as of opening it.
  const [since] = useState(() => new Date(Date.now() - 24 * 3600_000).toISOString());
  const calls = useMcpInvocations({ serverUid, limit: 200, since });
  const [only, setOnly] = useState<"all" | "errors">("all");
  const [agent, setAgent] = useState<string>("all");
  const [openId, setOpenId] = useState<number | null>(null);

  const rows = useMemo(() => {
    const all = calls.data?.invocations ?? [];
    return all.filter(
      (r) => (only === "all" || r.status !== "ok") && (agent === "all" || r.agent_uid === agent),
    );
  }, [calls.data, only, agent]);
  const errors = (calls.data?.invocations ?? []).filter((r) => r.status !== "ok").length;
  const nameOf = (uid: string | null) =>
    agents.find((a) => a.uid === uid)?.display_name ?? t("mcp.page.unknownSession");
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
        <Segmented
          label={t("mcp.page.log.agent")}
          value={agent}
          onChange={setAgent}
          options={[
            { value: "all", label: t("agentBadge.allAgents") },
            ...agents.map((a) => ({ value: a.uid, label: a.display_name })),
          ]}
        />
      </div>
      {calls.isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : rows.length === 0 ? (
        <p className="text-xs text-text-muted">{t("mcp.page.noCalls")}</p>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <table className="w-full text-xs" aria-label={t("mcp.page.log.calls")}>
            <thead>
              <tr className="text-left text-text-muted">
                <th className="py-1 font-medium">{t("mcp.page.log.time")}</th>
                <th className="py-1 font-medium">{t("mcp.page.log.tool")}</th>
                <th className="py-1 font-medium">{t("mcp.page.calledBy")}</th>
                <th className="py-1 font-medium">{t("mcp.page.log.result")}</th>
                <th className="py-1 text-right font-medium">{t("mcp.page.log.took")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.id}
                  className={cn(
                    "cursor-pointer border-t border-border-subtle hover:bg-surface-hover",
                    r.id === openId && "bg-surface-selected",
                  )}
                  onClick={() => setOpenId(r.id === openId ? null : r.id)}
                >
                  <td className="py-1.5 tabular-nums">{shortTime(r.timestamp)}</td>
                  <td className="py-1.5 font-mono">{r.capability_key}</td>
                  <td className="py-1.5">{nameOf(r.agent_uid)}</td>
                  <td className={cn("py-1.5", r.status === "ok" ? "text-text" : "text-danger")}>
                    {t(`mcp.page.log.status.${r.status}`)}
                  </td>
                  <td className="py-1.5 text-right tabular-nums">{took(r.duration_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {open ? (
        <dl
          className="flex flex-col gap-1 rounded-md border border-border-subtle p-3 text-xs"
          data-testid="mcp-call-detail"
        >
          <div className="flex gap-3">
            <dt className="w-20 text-text-muted">{t("mcp.page.log.result")}</dt>
            <dd>{open.error_message ?? t(`mcp.page.log.status.${open.status}`)}</dd>
          </div>
          <div className="flex gap-3">
            <dt className="w-20 text-text-muted">{t("mcp.page.log.took")}</dt>
            <dd>{took(open.duration_ms)}</dd>
          </div>
          <div className="flex gap-3">
            <dt className="w-20 text-text-muted">{t("mcp.page.log.session")}</dt>
            <dd className="font-mono">{open.session_id ?? "—"}</dd>
          </div>
        </dl>
      ) : null}
      <p className="text-xs text-text-muted">{t("mcp.page.log.callsFootnote")}</p>
    </div>
  );
}
