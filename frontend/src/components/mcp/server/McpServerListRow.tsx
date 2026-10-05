// src/components/mcp/server/McpServerListRow.tsx — one server in the MCP servers list (design 4.1.01).
//
// A state dot, the server's fixed name in mono, a second line — the reason when it needs the user ("Connection
// refused · since 14:02", "Secret missing · LINEAR_API_KEY", "uvx is not
// installed"), else its transport and tool count — and its reach on the
// right: All agents, or the badges of the agents it is limited to; an Off
// server leaves it empty (its group already says it is off). The
// checkbox feeds the selection bar; like the Skills library's it shows on
// hover or focus, and on every row while any is ticked.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AgentBadgeGroup } from "@/components/agent/AgentBadgeGroup";
import { StatusDot } from "@/components/status/StatusDot";
import { Checkbox } from "@/components/ui/checkbox";
import type { AgentOut } from "@/lib/api/agents";
import type { ResourceOut } from "@/lib/api/resources";
import type { McpStatusDetail } from "@/lib/hooks/useMcpServerStatus";
import type { ToolTiering } from "@/lib/hooks/useMcpServerPage";
import { toneTextClass } from "@/lib/statusColors";
import { STATUS_TONE } from "@/lib/statusTone";
import { cn } from "@/lib/utils";
import { serverState, shortTime, transportOf, type ServerState } from "@/lib/mcp/serverState";

interface Props {
  resource: ResourceOut;
  detail: McpStatusDetail | null | undefined;
  tiering: ToolTiering | undefined;
  agents: readonly AgentOut[];
  to: string;
  current: boolean;
  /** Any row is ticked: every checkbox shows. */
  selecting?: boolean;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}

function Subline({
  state,
  resource,
  detail,
  tiering,
}: {
  state: ServerState;
  resource: ResourceOut;
  detail: McpStatusDetail | null | undefined;
  tiering: ToolTiering | undefined;
}) {
  const { t } = useTranslation();
  const warn = cn("truncate text-xs", toneTextClass(STATUS_TONE[state.tone]));
  if (state.kind === "launcherMissing") {
    return (
      <span className={warn}>
        {t("mcp.page.reason.launcher", { runner: detail?.missing_runner })}
      </span>
    );
  }
  if (state.kind === "secretMissing") {
    return (
      <span className={warn}>
        {t("mcp.page.reason.secret", {
          secret: detail?.missing_secret,
        })}
      </span>
    );
  }
  if (state.kind === "failing") {
    const error = detail?.last_error ?? t("mcp.page.reason.failing");
    return (
      <span className={warn}>
        {detail?.failing_since
          ? t("mcp.page.reason.failingSince", { error, since: shortTime(detail.failing_since) })
          : error}
      </span>
    );
  }
  const transport = transportOf(resource.config);
  const parts = [t(`mcp.page.transport.${transport.type}`)];
  if (tiering && tiering.tool_count > 0)
    parts.push(t("mcp.page.toolCount", { count: tiering.tool_count }));
  return <span className="truncate text-xs text-text-muted">{parts.join(" · ")}</span>;
}

function ReachMark({ resource, agents }: { resource: ResourceOut; agents: readonly AgentOut[] }) {
  const { t } = useTranslation();
  if (!resource.enabled) return null;
  const scoped = resource.scope?.agents ?? null;
  if (scoped === null)
    return <span className="text-xs text-text-muted">{t("agentBadge.allAgents")}</span>;
  const chosen = agents.filter((a) => scoped.includes(a.uid));
  if (chosen.length === 0)
    return <span className="text-xs text-text-muted">{t("scope.noneSelected")}</span>;
  return (
    <AgentBadgeGroup
      agents={chosen.map((a) => ({ type: a.type, name: a.display_name }))}
      total={agents.length}
      className="text-xs text-text-muted"
    />
  );
}

export function McpServerListRow({
  resource,
  detail,
  tiering,
  agents,
  to,
  current,
  selecting = false,
  checked,
  onCheckedChange,
}: Props) {
  const { t } = useTranslation();
  const state = serverState(resource, detail);
  const label = resource.name;
  return (
    <li
      className={cn(
        "group flex items-center gap-2 rounded-lg pl-2.5 transition-colors duration-fast",
        current ? "bg-surface-selected" : "hover:bg-surface-hover",
      )}
    >
      <span
        className={cn(
          "shrink-0 items-center",
          selecting || checked
            ? "inline-flex"
            : "hidden group-focus-within:inline-flex group-hover:inline-flex",
        )}
      >
        <Checkbox
          checked={checked}
          onChange={(e) => onCheckedChange(e.target.checked)}
          aria-label={`${t("common.bulk.selectRow")}: ${resource.name}`}
        />
      </span>
      <Link
        to={to}
        aria-current={current ? "page" : undefined}
        className="flex min-w-0 flex-1 items-center gap-2.5 rounded-lg py-2 pr-2.5 text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring"
      >
        <StatusDot tone={state.tone} />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className={"truncate font-mono text-xs font-label"}>{label}</span>
          <Subline state={state} resource={resource} detail={detail} tiering={tiering} />
        </span>
        <span className="shrink-0">
          <ReachMark resource={resource} agents={agents} />
        </span>
      </Link>
    </li>
  );
}
