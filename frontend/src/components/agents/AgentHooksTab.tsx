// src/components/agents/AgentHooksTab.tsx — the agent's Hooks tab: every hook it will run, in one table.
//
// Spec agent-registry "List every hook in the agent's native config" and
// "Filter an agent's installed kinds by owner". Read only: the hooks are shown
// grouped by event (AgentHooksByEvent) — what runs on PreToolUse, on
// SessionStart, … — and nothing opens a file. Coffer's own hook is marked, and
// its health, Codex's trust and its last fire are said once in a status block
// that offers Repair when it is out of date or missing (`onRepair`, wired by the
// detail page to the connection-change dialog). A file that does not parse is a
// warning above the list, not a failure of the tab.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Webhook } from "lucide-react";

import { AgentHooksByEvent } from "@/components/agents/AgentHooksByEvent";
import { AgentKindTab } from "@/components/agents/tabs/AgentKindTab";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import { hookRows, hookSummaryCounts, type HookRow } from "@/lib/agents/hookRows";
import type { AgentOut } from "@/lib/api/agents";
import { useAgentHooks } from "@/lib/hooks/useAgents";

interface Props {
  agent: AgentOut;
  /** Reinstall Coffer's hook (the Coffer connection's repair). Repair shows only when given. */
  onRepair?: () => void;
}

const searchText = (row: HookRow) =>
  `${row.event} ${row.command ?? ""} ${row.path} ${row.matcher ?? ""} ${row.plugin ?? ""}`;

export function AgentHooksTab({ agent, onRepair }: Props) {
  const { t } = useTranslation();
  const hooks = useAgentHooks(agent.uid);
  const rows = useMemo(() => hookRows(hooks.data), [hooks.data]);
  const counts = hookSummaryCounts(hooks.data);
  const agentName = agentTypeLabel(agent.type);
  const parseErrors = hooks.data?.parse_errors ?? [];

  const summary = [
    `${t("agents.hooksTab.summary.hooks", { count: counts.hooks })} ${t(
      "agents.hooksTab.summary.files",
      { count: counts.files },
    )}`,
    counts.cofferMissing
      ? t("agents.hooksTab.summary.cofferMissing")
      : counts.coffer > 0
        ? t("agents.hooksTab.summary.coffer", { count: counts.coffer })
        : null,
    t("agents.hooksTab.summary.own", { count: counts.own }),
  ]
    .filter(Boolean)
    .join(" · ");

  const cofferRow = rows.find((r) => r.owner === "coffer") ?? null;

  return (
    <div className="flex flex-col gap-3.5">
      {parseErrors.length > 0 ? (
        <Alert variant="warning">
          <AlertDescription>
            <ul className="space-y-0.5">
              {parseErrors.map((pe) => (
                <li key={`${pe.source}:${pe.path}`} className="break-all">
                  {t("agents.hooksTab.parseError", {
                    file: abbreviateHomePath(pe.path),
                    error: pe.error,
                  })}
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      ) : null}
      <AgentKindTab
        rows={rows}
        summary={summary}
        searchPlaceholder={t("agents.hooksTab.search")}
        searchText={searchText}
        isLoading={hooks.isPending}
        error={hooks.error}
        onRetry={() => void hooks.refetch()}
        empty={{
          icon: Webhook,
          title: t("agents.hooksTab.emptyTitle", { agent: agentName }),
          description: t("agents.hooksTab.emptyBody", { agent: agentName }),
        }}
        footnote={t("agents.hooksTab.footnote", { agent: agentName })}
      >
        {(visible) => (
          <AgentHooksByEvent
            rows={visible}
            cofferRow={cofferRow}
            agentType={agent.type}
            onRepair={onRepair}
            onCheckAgain={() => void hooks.refetch()}
            checking={hooks.isFetching}
          />
        )}
      </AgentKindTab>
    </div>
  );
}
