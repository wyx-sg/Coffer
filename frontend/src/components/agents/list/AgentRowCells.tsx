// src/components/agents/list/AgentRowCells.tsx — the cells of one Agents row that read more than the type row.
//
// Each cell is its own component so it can read the query it needs; the
// reads are the ones the detail page's tabs make, so the counts here agree
// with the tables they summarise. A type not added reads nothing and shows —.
import { useTranslation } from "react-i18next";

import { ActionMenu } from "@/components/ui/menu";
import { StatusWord } from "@/components/status/StatusWord";
import { TableActionButton } from "@/components/table/TableActionButton";
import { AgentBadge } from "@/components/agent/AgentBadge";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import { agentRowStateKey, agentRowTone, type AgentRowState } from "@/lib/agents/rowState";
import type { AgentTypeOut } from "@/lib/api/agents";
import { useAgent, useAgentConnection, useAgentHooks } from "@/lib/hooks/useAgents";
import { useAgentCounts } from "@/lib/hooks/useAgentCounts";
import { formatRelativeTime } from "./relativeTime";
import { useAgentRowActions } from "./useAgentRowActions";

const DASH = "—";

export function AgentNameCell({ row }: { row: AgentTypeOut }) {
  const { t } = useTranslation();
  const sub =
    row.state === "config_only"
      ? t("agents.list.sub.leftBehind")
      : row.state === "missing"
        ? t(row.uid ? "agents.state.not_found" : "agents.state.not_installed")
        : row.state === "installed_never_run"
          ? t("agents.state.never_run")
          : row.version
            ? t("agents.list.sub.installedVersion", { version: row.version })
            : t("agents.list.sub.installed");
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <AgentBadge type={row.type} tooltip={false} />
      <div className="flex min-w-0 flex-col">
        <span className="text-sm font-label text-text">{agentTypeLabel(row.type)}</span>
        <span className="text-xs text-text-muted">{sub}</span>
      </div>
    </div>
  );
}

export function ConfigDirCell({ row }: { row: AgentTypeOut }) {
  const { t } = useTranslation();
  return (
    <span className="break-all font-mono text-xs text-text">
      {abbreviateHomePath(row.config_dir)}
      {row.state === "installed_never_run" ? (
        <span className="ml-1.5 font-sans text-text-subtle">{t("agents.list.notCreated")}</span>
      ) : null}
    </span>
  );
}

export function ModelCell({ uid }: { uid: string | null }) {
  const model = useAgent(uid ?? "").data?.model;
  return <span className="break-all font-mono text-xs text-text">{(uid && model) || DASH}</span>;
}

type CountKind = "skills" | "mcp" | "plugins";

function RegisteredCount({ uid, kind }: { uid: string; kind: CountKind }) {
  const counts = useAgentCounts(uid);
  const value =
    kind === "plugins"
      ? counts.plugins?.total
      : counts[kind]
        ? counts[kind].coffer + counts[kind].own
        : undefined;
  return <span className="text-sm tabular-nums text-text">{value ?? DASH}</span>;
}

export function CountCell({ uid, kind }: { uid: string | null; kind: CountKind }) {
  if (!uid) return <span className="text-sm text-text-subtle">{DASH}</span>;
  return <RegisteredCount uid={uid} kind={kind} />;
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
    case "not_connected":
      return t("agents.list.detail.notConnected");
    case "not_added":
      return t("agents.list.detail.found", { dir });
    case "never_run":
      return t("agents.list.detail.notCreatedYet", { dir });
    case "not_found":
      return t("agents.list.detail.gone", { dir });
    case "disabled":
      return t("agents.list.detail.disabled");
    case "not_installed":
      return t("agents.list.detail.installByAgent");
    case "config_left_behind":
      return t("agents.list.detail.reinstallByAgent", { dir });
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
  if (!state) return null;
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <StatusWord tone={agentRowTone(state)}>{t(agentRowStateKey(state))}</StatusWord>
      <span className="text-xs text-text-muted">
        <CofferDetail row={row} state={state} />
      </span>
    </div>
  );
}

export function ActionsCell({ row }: { row: AgentTypeOut }) {
  const { t } = useTranslation();
  const { primary, actions, dialogs } = useAgentRowActions(row, { includeOpen: true });
  const name = agentTypeLabel(row.type);
  return (
    <div className="flex items-center justify-end gap-1">
      {primary ? (
        <TableActionButton
          icon={primary.icon}
          label={primary.label}
          destructive={primary.destructive}
          onClick={primary.run}
        />
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
