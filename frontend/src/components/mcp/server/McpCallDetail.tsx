// src/components/mcp/server/McpCallDetail.tsx — the chosen call under the calls list: when, what, who; its result, how long it took, its session (design 4.1.22).
import { useTranslation } from "react-i18next";

import { StatusDot } from "@/components/status/StatusDot";
import type { components } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { callTone, seconds } from "@/lib/mcp/serverState";

type Invocation = components["schemas"]["InvocationOut"];

function clock(iso: string): string {
  const at = new Date(iso);
  return Number.isNaN(at.getTime())
    ? iso
    : at.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

interface Props {
  call: Invocation;
  agentName: string;
}

export function McpCallDetail({ call, agentName }: Props) {
  const { t } = useTranslation();
  const ok = call.status === "ok";
  const tone = callTone(call.status);
  const rows: [string, JSX.Element][] = [
    [
      t("mcp.page.log.result"),
      <span
        key="r"
        className={cn("inline-flex items-center gap-1.5", ok ? "text-text" : "text-danger")}
      >
        <StatusDot tone={tone} />
        {call.error_message ?? t(`mcp.page.log.status.${call.status}`)}
      </span>,
    ],
    [
      t("mcp.page.log.took"),
      <span key="t">
        {ok
          ? seconds(call.duration_ms)
          : t("mcp.page.log.gaveUp", { took: seconds(call.duration_ms) })}
      </span>,
    ],
    [
      t("mcp.page.log.session"),
      <span key="s" className="font-mono">
        {call.session_id ?? "—"}
      </span>,
    ],
  ];
  return (
    <div
      className="flex flex-col gap-1 rounded-lg bg-surface-sunken px-3 py-2.5 text-xs"
      data-testid="mcp-call-detail"
    >
      <p className="pb-1 font-semibold text-text">
        {clock(call.timestamp)} · {call.capability_key} · {agentName}
      </p>
      <dl className="flex flex-col">
        {rows.map(([label, value]) => (
          <div
            key={label}
            className="flex gap-3 border-b border-border-subtle py-2 last:border-b-0"
          >
            <dt className="w-24 shrink-0 text-text-muted">{label}</dt>
            <dd className="min-w-0 text-text">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="pt-1 text-text-muted">{t("mcp.page.log.callsFootnote")}</p>
    </div>
  );
}
