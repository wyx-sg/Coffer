// src/components/mcp/server/McpCallDrawer.tsx — one invocation opened from the Invocations tab: a 640 drawer (design 4.1.13).
//
// The tool and how it ended up top, one line of when · who · how long, then
// Result / Error / Server / Called by / Started / Took, and the footnote that
// Coffer never records arguments or results. A stdio server's drawer ends
// with View server log; a Streamable HTTP server has none.
import { useTranslation } from "react-i18next";
import { SquareTerminal } from "lucide-react";

import { StatusDot } from "@/components/status/StatusDot";
import { Button } from "@/components/ui/button";
import type { components } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { callTone, seconds } from "@/lib/mcp/serverState";
import { McpDrawer } from "./McpDrawer";

type Invocation = components["schemas"]["InvocationOut"];

function clock(iso: string): string {
  const at = new Date(iso);
  return Number.isNaN(at.getTime())
    ? iso
    : at.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function started(iso: string): string {
  const at = new Date(iso);
  return Number.isNaN(at.getTime())
    ? iso
    : at.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
}

interface Props {
  call: Invocation | null;
  agentName: string;
  serverName: string;
  /** "stdio" servers have a log of their own; HTTP ones do not. */
  transport: "stdio" | "http" | "unknown";
  onClose: () => void;
  onViewLog: () => void;
}

export function McpCallDrawer({
  call,
  agentName,
  serverName,
  transport,
  onClose,
  onViewLog,
}: Props) {
  const { t } = useTranslation();
  const ok = call?.status === "ok";
  const rows: [string, JSX.Element | string | null][] = call
    ? [
        [t("mcp.page.log.result"), t(`mcp.page.log.status.${call.status}`)],
        [t("mcp.page.log.error"), call.error_message],
        [t("mcp.page.log.server"), `${serverName} · ${t(`mcp.page.transport.${transport}`)}`],
        [t("mcp.page.calledBy"), agentName],
        [t("mcp.page.log.started"), started(call.timestamp)],
        [t("mcp.page.log.took"), seconds(call.duration_ms)],
      ]
    : [];
  return (
    <McpDrawer
      open={call !== null}
      onClose={onClose}
      testId="mcp-call-drawer"
      title={
        call ? (
          <>
            <span className="truncate font-mono">{call.capability_key}</span>
            <span
              className={cn(
                "inline-flex shrink-0 items-center gap-1.5 text-xs font-label",
                ok ? "text-text-muted" : "text-danger",
              )}
            >
              {ok ? null : <StatusDot tone={callTone(call.status)} />}
              {t(`mcp.page.log.status.${call.status}`)}
            </span>
          </>
        ) : null
      }
      subtitle={
        call ? `${clock(call.timestamp)} · ${agentName} · ${seconds(call.duration_ms)}` : undefined
      }
      footer={
        transport === "stdio" ? (
          <Button size="sm" variant="outline" onClick={onViewLog}>
            <SquareTerminal aria-hidden /> {t("mcp.page.log.viewServerLog")}
          </Button>
        ) : undefined
      }
    >
      <dl className="flex flex-col" data-testid="mcp-call-detail">
        {rows.map(([label, value]) =>
          value === null ? null : (
            <div
              key={label}
              className="flex gap-3 border-b border-border-subtle py-2.5 text-xs last:border-b-0"
            >
              <dt className="w-24 shrink-0 text-text-muted">{label}</dt>
              <dd className="min-w-0 break-words text-text">{value}</dd>
            </div>
          ),
        )}
      </dl>
      <p className="text-xs text-text-muted">{t("mcp.page.log.callsFootnote")}</p>
    </McpDrawer>
  );
}
