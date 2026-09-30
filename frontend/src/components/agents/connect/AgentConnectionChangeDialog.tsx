// src/components/agents/connect/AgentConnectionChangeDialog.tsx — spec agent-registry "Show the Coffer connection on the agent pages".
//
// Add, Connect, Repair and Disconnect all go through this one review: every
// file the change writes, the lines Coffer adds or takes out, and a sentence
// per agent on what it gets or loses — nothing is written until the user
// confirms. The items are frozen at Apply, so the connection read refreshing
// under a running write does not reshape the list being ticked off.
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  ChangePreview,
  type ChangeItem,
  type ChangePreviewState,
} from "@/components/change-preview/ChangePreview";
import {
  createsConfigDir,
  partsToInstall,
  planConnect,
  planDisconnect,
  type ConnectionPartKey,
  type PlanAgent,
} from "@/lib/agents/connectionPlan";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import type { AgentTypeOut } from "@/lib/api/agents";
import { useAgentConnection } from "@/lib/hooks/useAgents";
import { useConnectionChangeRun } from "./useConnectionChangeRun";

export type ConnectionChangeRequest =
  | { kind: "add"; rows: AgentTypeOut[] }
  | { kind: "connect"; row: AgentTypeOut }
  | { kind: "disconnect"; row: AgentTypeOut };

interface Props {
  request: ConnectionChangeRequest | null;
  onClose: () => void;
}

interface Snapshot {
  items: ChangeItem[];
  summaries: { agentType: string; text: string }[];
  /** Repair (some parts already in place) rather than Connect. */
  repairing: boolean;
}

const FILE_NAME: Record<string, Record<ConnectionPartKey, string>> = {
  claude_code: { mcp: ".claude.json", memory_hook: "settings.json" },
  codex: { mcp: "config.toml", memory_hook: "hooks.json" },
};

export function AgentConnectionChangeDialog({ request, onClose }: Props) {
  const { t } = useTranslation();
  const single = request && request.kind !== "add" ? request.row : undefined;
  const uid = single?.uid ?? "";
  const connection = useAgentConnection(uid);
  const runner = useConnectionChangeRun(request?.kind, uid);
  const [frozen, setFrozen] = useState<Snapshot | null>(null);
  const rows = useMemo(
    () => (!request ? [] : request.kind === "add" ? request.rows : [request.row]),
    [request],
  );

  const { reset } = runner;
  useEffect(() => {
    // A new request starts a fresh review.
    setFrozen(null);
    reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when the request changes
  }, [request]);

  const agents: PlanAgent[] = rows.map((row) =>
    request?.kind === "add" ? { row } : { row, uid: row.uid, parts: connection.data?.parts },
  );
  const computing =
    !!request && request.kind !== "add" && (connection.isPending || !connection.data);

  const plan = useMemo<Snapshot>(() => {
    if (!request || computing) return { items: [], summaries: [], repairing: false };
    const opts = {
      placeholders: {
        uid: t("agents.change.placeholder.uid"),
        shim: t("agents.change.placeholder.shim"),
      },
    };
    const items =
      request.kind === "disconnect" ? planDisconnect(agents, opts) : planConnect(agents, opts);
    const summaries = agents.map((agent) => {
      const type = agent.row.type;
      if (request.kind === "disconnect") {
        return { agentType: type, text: t("agents.change.summary.loses") };
      }
      const parts = partsToInstall(agent);
      const files = { mcpFile: FILE_NAME[type].mcp, hookFile: FILE_NAME[type].memory_hook };
      const gets =
        parts.length > 1 ? "both" : parts[0] === "memory_hook" ? "hook" : ("mcp" as const);
      const sentences = [t(`agents.change.summary.gets.${gets}`, files)];
      if (createsConfigDir(agent)) {
        sentences.push(
          t("agents.change.summary.creates", { dir: abbreviateHomePath(agent.row.config_dir) }),
        );
      }
      sentences.push(t(`agents.change.summary.keeps.${type}`));
      return { agentType: type, text: sentences.join(" ") };
    });
    const repairing = !!connection.data?.parts.some((p) => p.installed);
    return { items, summaries, repairing };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `agents` derives from request + connection
  }, [request, computing, connection.data, t]);

  const shown = frozen ?? plan;
  const items = shown.items.map((item) => {
    const p = runner.progress[item.agentType as AgentTypeOut["type"]];
    return p ? { ...item, status: p.status, error: p.error } : item;
  });
  const failedAny = items.some((i) => i.status === "failed");

  let state: ChangePreviewState;
  if (runner.phase === "applying") state = "applying";
  else if (runner.phase === "done") state = failedAny ? "failed" : "applied";
  else if (computing) state = "computing";
  else state = plan.items.length === 0 ? "empty" : "ready";

  const name = single ? agentTypeLabel(single.type) : "";
  const subtitle = !request
    ? undefined
    : request.kind === "add"
      ? request.rows.length > 1
        ? t("agents.change.subtitle.addMany", { count: request.rows.length })
        : t("agents.change.subtitle.connect", { name: agentTypeLabel(request.rows[0].type) })
      : request.kind === "disconnect"
        ? t("agents.change.title")
        : t(shown.repairing ? "agents.change.subtitle.repair" : "agents.change.subtitle.connect", {
            name,
          });
  const disconnect = request?.kind === "disconnect";

  const apply = () => {
    setFrozen(plan);
    void runner.run(rows);
  };
  const retry = (failedIds: string[]) => {
    const types = new Set(items.filter((i) => failedIds.includes(i.id)).map((i) => i.agentType));
    void runner.run(rows.filter((row) => types.has(row.type)));
  };

  return (
    <ChangePreview
      open={!!request}
      onOpenChange={(open) => !open && onClose()}
      title={disconnect ? t("agents.change.disconnect.title", { name }) : t("agents.change.title")}
      subtitle={subtitle}
      state={state}
      items={items}
      summaries={shown.summaries}
      onApply={apply}
      onRetry={retry}
      activityHref="/activity"
      applyLabel={disconnect ? t("agents.change.disconnect.confirm") : undefined}
      applyDestructive={disconnect}
      note={disconnect ? t("agents.change.disconnect.note") : undefined}
    />
  );
}
