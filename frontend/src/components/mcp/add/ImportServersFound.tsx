// frontend/src/components/mcp/add/ImportServersFound.tsx — the "Servers found"
// checklist heading the import review (board 4.1.18).
//
// One row per server the daemon planned from every direct entry: its name,
// the badges of the agents that hold it, and what importing it means when
// that is not plain — two agents' entries merging into one server, a
// duplicate of a server Coffer already has, or a name that cannot be
// registered (never ticked). Ticking a row ticks all of its entries.
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Checkbox } from "@/components/ui/checkbox";
import type { AgentOut, McpEntryOut } from "@/lib/api/agents";
import { translateApiError } from "@/lib/api/errors";
import type { McpImportPlan } from "@/lib/api/mcpImport";
import { entryKey } from "./importPlanItems";

const LABEL = "text-2xs font-semibold uppercase tracking-[.04em] text-text-subtle";

interface Props {
  /** The plan of importing every direct entry; undefined while it loads. */
  plan: McpImportPlan | undefined;
  groups: { agent: AgentOut; entries: McpEntryOut[]; duplicates: McpEntryOut[] }[];
  /** The entry keys ticked now. */
  chosen: ReadonlySet<string>;
  error: unknown;
  onToggle: (keys: string[], on: boolean) => void;
  busy: boolean;
}

export function ImportServersFound({ plan, groups, chosen, error, onToggle, busy }: Props) {
  const { t } = useTranslation();
  const typeOf = (uid: string) => groups.find((g) => g.agent.uid === uid)?.agent.type ?? "";
  const servers = plan?.servers ?? [];
  return (
    <div className="flex flex-col gap-2">
      {error ? (
        <Alert variant="error">
          <AlertDescription>{translateApiError(t, error)}</AlertDescription>
        </Alert>
      ) : null}
      <span className={LABEL}>{t("mcp.import.serversFound", { count: servers.length })}</span>
      {plan && servers.length === 0 ? (
        <p className="text-xs text-text-muted">{t("mcp.import.none")}</p>
      ) : null}
      <ul className="flex flex-col gap-1.5">
        {servers.map((server) => {
          const keys = server.entries.map(entryKey);
          const ticked = server.name_usable && keys.some((k) => chosen.has(k));
          const agents = [...new Set(server.entries.map((e) => e.agent_uid))];
          const note = !server.name_usable
            ? t("mcp.import.nameUnusable")
            : server.op === "duplicate"
              ? t("mcp.import.duplicateNote")
              : server.merged
                ? t("mcp.import.mergedNote")
                : null;
          return (
            <li key={`${server.op}:${server.name}`} className="flex flex-col gap-0.5">
              <label className="flex cursor-pointer items-center gap-2.5">
                <Checkbox
                  checked={ticked}
                  disabled={!server.name_usable || busy}
                  aria-label={t("mcp.add.include", { name: server.name })}
                  onChange={(e) => onToggle(keys, e.target.checked)}
                />
                <span className="min-w-0 flex-1 truncate font-mono text-sm text-text">
                  {server.name}
                </span>
                <span className="inline-flex shrink-0 gap-1">
                  {agents.map((uid) => (
                    <AgentBadge key={uid} type={typeOf(uid)} size="sm" />
                  ))}
                </span>
              </label>
              {note ? (
                <p
                  className={
                    server.name_usable ? "pl-6 text-xs text-text-muted" : "pl-6 text-xs text-danger"
                  }
                >
                  {note}
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
