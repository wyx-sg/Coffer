// src/components/agents/list/AgentRowCells.tsx — the cells of one Agents row that read more than the type row.
//
// Each cell is its own component so it can read the query it needs; the
// reads are the ones the detail page's tabs make, so the counts here agree
// with the tables they summarise. A type not added reads nothing and shows —.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ActionMenu } from "@/components/ui/menu";
import { StatusWord } from "@/components/status/StatusWord";
import { TableActionButton } from "@/components/table/TableActionButton";
import { AgentBadge } from "@/components/agent/AgentBadge";
import { abbreviateHomePath, agentProgramName, agentTypeLabel } from "@/lib/agents/display";
import { agentTabPath, type AgentTab } from "@/lib/agents/routes";
import { agentRowStateKey, agentRowTone, type AgentRowState } from "@/lib/agents/rowState";
import type { AgentTypeOut } from "@/lib/api/agents";
import { useAgent, useAgentConnection, useAgentHooks } from "@/lib/hooks/useAgents";
import { useAgentCounts } from "@/lib/hooks/useAgentCounts";
import { useAgentDefaultModel } from "@/lib/hooks/useAgentModels";
import { useAgentPending } from "@/lib/hooks/useAgentPending";
import { cn } from "@/lib/utils";
import { AgentPendingStatus } from "./AgentPendingStatus";
import { formatRelativeTime } from "./relativeTime";
import { useAgentRowActions } from "./useAgentRowActions";

const DASH = "—";

export function AgentNameCell({ row }: { row: AgentTypeOut }) {
  const { t } = useTranslation();
  // Only the version: the state is the Coffer column's word, and a program that
  // is not on this Mac has no version to give.
  const sub =
    row.state === "config_only" || row.state === "missing" || !row.version
      ? null
      : t("agents.list.sub.version", { version: row.version });
  const pending = useAgentPending(row);
  return (
    <div className={cn("flex min-w-0 items-center gap-2.5", pending && "opacity-60")}>
      <AgentBadge type={row.type} tooltip={false} />
      <div className="flex min-w-0 flex-col">
        <span className="truncate text-sm font-label text-text">{agentTypeLabel(row.type)}</span>
        {sub ? <span className="truncate text-xs text-text-muted">{sub}</span> : null}
      </div>
    </div>
  );
}

export function ConfigDirCell({ row }: { row: AgentTypeOut }) {
  return (
    <span className="break-all font-mono text-xs text-text">
      {abbreviateHomePath(row.config_dir)}
    </span>
  );
}

/** The agent's default model. On a Coffer connection that is the agent's binding; on its own
 *  login it is what the agent's own config names — and when that names none, the agent chooses
 *  for itself, which is said in words rather than guessed from the first catalogue entry. */
export function ModelCell({ uid, type }: { uid: string | null; type: AgentTypeOut["type"] }) {
  const { t } = useTranslation();
  const agent = useAgent(uid ?? "").data;
  const onConnection = !!agent?.connection_uid;
  const own = useAgentDefaultModel(onConnection ? "" : type).data ?? null;
  if (!uid || !agent) return <span className="font-mono text-xs text-text">{DASH}</span>;
  const model = onConnection ? agent.model : own;
  if (model) return <span className="block truncate whitespace-nowrap font-mono text-xs text-text">{model}</span>;
  return (
    <span className="whitespace-nowrap text-xs text-text-subtle">
      {onConnection ? DASH : t("agents.list.autoModel")}
    </span>
  );
}

type CountKind = "skills" | "mcp" | "plugins";

/** The detail tab each count links to. */
const COUNT_TAB: Record<CountKind, AgentTab> = {
  skills: "skills",
  mcp: "mcp-servers",
  plugins: "plugins",
};

function RegisteredCount({ row, uid, kind }: { row: AgentTypeOut; uid: string; kind: CountKind }) {
  const counts = useAgentCounts(uid);
  const value =
    kind === "plugins"
      ? counts.plugins?.total
      : counts[kind]
        ? counts[kind].coffer + counts[kind].own
        : undefined;
  if (value === undefined) return <span className="text-sm tabular-nums text-text">{DASH}</span>;
  // The row itself opens the agent; a count opens that tab instead.
  return (
    <Link
      to={agentTabPath(row.type, COUNT_TAB[kind])}
      onClick={(event) => event.stopPropagation()}
      className="text-sm tabular-nums text-text underline-offset-2 hover:underline"
    >
      {value}
    </Link>
  );
}

export function CountCell({ row, kind }: { row: AgentTypeOut; kind: CountKind }) {
  if (!row.uid) return <span className="text-sm text-text-subtle">{DASH}</span>;
  return <RegisteredCount row={row} uid={row.uid} kind={kind} />;
}

/** The muted line under the state word: what the state means for this agent. */
function CofferDetail({ row, state }: { row: AgentTypeOut; state: AgentRowState }) {
  const { t, i18n } = useTranslation();
  const uid = row.uid ?? "";
  const parts = useAgentConnection(uid).data?.parts;
  const hook = useAgentHooks(uid).data?.coffer_hook;
  const dir = abbreviateHomePath(row.config_dir);
  switch (state) {
    case "connected":
      if (!parts?.some((p) => p.key === "memory_hook")) return null;
      return hook?.last_fired_at
        ? t("agents.list.detail.lastDelivery", {
            when: formatRelativeTime(hook.last_fired_at, i18n.language),
          })
        : t("agents.list.detail.noDelivery");
    case "needs_repair": {
      const missing = (parts ?? []).filter((p) => !p.installed).map((p) => p.key);
      return missing
        .map((key) =>
          key === "mcp"
            ? t("agents.list.detail.mcpMissing")
            : hook?.health === "stale"
              ? t("agents.list.detail.hookStale")
              : t("agents.list.detail.hookMissing"),
        )
        .join(" · ");
    }
    // One off state: the word says it all, and the Connect button is the next step.
    case "not_connected":
    case "not_added":
    case "never_run":
      return null;
    case "not_found":
      return t("agents.list.detail.gone", { dir });
    case "disabled":
      return t("agents.list.detail.disabled");
    case "not_installed":
      return t("agents.list.detail.notOnThisMac");
    case "config_left_behind":
      return t("agents.list.detail.keptNotOnPath", {
        dir,
        program: agentProgramName(row.type),
      });
    case "checking":
      return null;
  }
}

export function CofferCell({
  row,
  state,
}: {
  row: AgentTypeOut;
  state: AgentRowState | undefined;
}) {
  const { t } = useTranslation();
  const pending = useAgentPending(row);
  if (!state) return null;
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      {pending ? (
        <AgentPendingStatus pending={pending} />
      ) : (
        <>
          <StatusWord tone={agentRowTone(state)}>{t(agentRowStateKey(state))}</StatusWord>
          <span className="text-xs text-text-muted">
            <CofferDetail row={row} state={state} />
          </span>
        </>
      )}
    </div>
  );
}

export function ActionsCell({ row }: { row: AgentTypeOut }) {
  const { t } = useTranslation();
  const { primary, actions, dialogs, pending } = useAgentRowActions(row, { inList: true });
  const name = agentTypeLabel(row.type);
  return (
    <div className="flex items-center justify-end gap-1">
      {primary ? (
        <TableActionButton label={primary.label} loading={!!pending} onClick={primary.run} />
      ) : null}
      <ActionMenu label={t("agents.rowMenu.label", { name })} actions={actions} />
      {/* A dialog is portalled but its clicks still bubble through React to
          the row, which would open the agent under it. */}
      <span className="contents" onClick={(event) => event.stopPropagation()}>
        {dialogs}
      </span>
    </div>
  );
}
