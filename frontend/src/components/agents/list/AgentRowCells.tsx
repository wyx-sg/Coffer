// src/components/agents/list/AgentRowCells.tsx — the cells of one Agents row that read more than the type row.
//
// Each cell is its own component so it can read the query it needs; the
// reads are the ones the detail page's tabs make, so the counts here agree
// with the tables they summarise. A type not added reads nothing and shows —.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { ActionMenu } from "@/components/ui/menu";
import { StatusWord } from "@/components/status/StatusWord";
import { TableActionButton } from "@/components/table/TableActionButton";
import { AgentBadge } from "@/components/agent/AgentBadge";
import { abbreviateHomePath, agentProgramName, agentTypeLabel } from "@/lib/agents/display";
import { agentTabPath, type AgentTab } from "@/lib/agents/routes";
import { agentRowStateKey, agentRowTone, type AgentRowState } from "@/lib/agents/rowState";
import type { AgentOut, AgentTypeOut } from "@/lib/api/agents";
import { useAgent, useAgentConnection, useAgentHooks } from "@/lib/hooks/useAgents";
import { useAgentCounts } from "@/lib/hooks/useAgentCounts";
import { useAgentDefaultModel } from "@/lib/hooks/useAgentModels";
import { useAgentPending } from "@/lib/hooks/useAgentPending";
import { useFeatureEnabled } from "@/lib/hooks/useFeatures";
import { cn } from "@/lib/utils";
import { useProviderLabel } from "../overview/useProviderLabel";
import { AgentPendingStatus } from "./AgentPendingStatus";
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
    <span
      className="block truncate whitespace-nowrap font-mono text-xs text-text"
      title={abbreviateHomePath(row.config_dir)}
    >
      {abbreviateHomePath(row.config_dir)}
    </span>
  );
}

/** Which provider the agent's turns go to: the Coffer connection it runs on, or its own built-in
 *  login — the Overview tab's Provider line. With the Models feature off no connection can be
 *  active, so it is the built-in login. */
function ProviderLabel({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const models = useFeatureEnabled("models") === true;
  const label = useProviderLabel(agent);
  const text = label ?? (models ? null : t(`agents.overviewTab.model.builtin.${agent.type}`));
  if (!text) return <span className="text-xs text-text-subtle">{DASH}</span>;
  return (
    <span className="block truncate whitespace-nowrap text-xs text-text" title={text}>
      {text}
    </span>
  );
}

function RegisteredProvider({ uid }: { uid: string }) {
  const agent = useAgent(uid).data;
  if (!agent) return <span className="text-xs text-text">{DASH}</span>;
  return <ProviderLabel agent={agent} />;
}

export function ProviderCell({ uid }: { uid: string | null }) {
  if (!uid) return <span className="text-xs text-text">{DASH}</span>;
  return <RegisteredProvider uid={uid} />;
}

/** The agent's default model. On a Coffer connection that is the agent's binding; on its own
 *  login it is what the agent's own config names — and when that names none, the agent runs its
 *  built-in default, which is said in words rather than guessed from the first catalogue entry. */
export function ModelCell({ uid, type }: { uid: string | null; type: AgentTypeOut["type"] }) {
  const { t } = useTranslation();
  const agent = useAgent(uid ?? "").data;
  const onConnection = !!agent?.connection_uid;
  const own = useAgentDefaultModel(onConnection ? "" : type).data ?? null;
  if (!uid || !agent) return <span className="font-mono text-xs text-text">{DASH}</span>;
  const model = onConnection ? agent.model : own;
  if (model)
    return (
      <span className="block truncate whitespace-nowrap font-mono text-xs text-text" title={model}>
        {model}
      </span>
    );
  return (
    <span className="whitespace-nowrap text-xs text-text-subtle">
      {onConnection ? DASH : t("agents.list.builtinDefault")}
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
  const { t } = useTranslation();
  const uid = row.uid ?? "";
  const parts = useAgentConnection(uid).data?.parts;
  const hook = useAgentHooks(uid).data?.coffer_hook;
  const dir = abbreviateHomePath(row.config_dir);
  switch (state) {
    // The word says it all; when the hook last fired is on the agent's Hooks tab.
    case "connected":
      return null;
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
  const { primary, handoff, pending, dialogs } = useAgentRowActions(row, { inList: true });
  return (
    <div className="flex items-center justify-end gap-1">
      {primary ? (
        <TableActionButton label={primary.label} loading={!!pending} onClick={primary.run} />
      ) : null}
      {handoff ? (
        // A click in the split button or its menu must not open the agent under it.
        <span className="contents" onClick={(event) => event.stopPropagation()}>
          <AgentHandoff prompt={handoff} size="sm" help={false} />
        </span>
      ) : null}
      {/* The dialogs of the button and of the ⋯ menu (their state is shared, see
          useRowDialogState) are drawn once, here. A dialog is portalled but its
          clicks still bubble through React to the row, which would open the
          agent under it. */}
      <span className="contents" onClick={(event) => event.stopPropagation()}>
        {dialogs}
      </span>
    </div>
  );
}

/** The ⋯ column: the row menu alone. */
export function RowMenuCell({ row }: { row: AgentTypeOut }) {
  const { t } = useTranslation();
  const { actions } = useAgentRowActions(row, { inList: true });
  const name = agentTypeLabel(row.type);
  if (actions.length === 0) return null;
  return (
    <div className="flex items-center justify-end">
      <ActionMenu label={t("agents.rowMenu.label", { name })} actions={actions} />
    </div>
  );
}
