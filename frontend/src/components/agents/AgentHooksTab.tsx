// src/components/agents/AgentHooksTab.tsx — the agent's Hooks tab: every hook it will run, in one table.
//
// Spec agent-registry "List every hook in the agent's native config" and
// "Filter an agent's installed kinds by owner". Read only apart from the row
// actions: each hook opens the file that declares it, and Coffer's own hook —
// marked, with its health, Codex's trust and its last fire — offers Repair when
// it is out of date or missing (`onRepair`, wired by the detail page to the
// connection-change dialog). A missing Coffer hook, which no file declares any
// more, still gets a row. A file that does not parse is a warning above the
// table, not a failure of the tab.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Webhook } from "lucide-react";

import { AgentHookCommandCell } from "@/components/agents/AgentHookCommandCell";
import { AgentHookEventCell } from "@/components/agents/AgentHookEventCell";
import { AgentHookRowActions } from "@/components/agents/AgentHookRowActions";
import { AgentHookStateCell } from "@/components/agents/AgentHookStateCell";
import { AgentKindTab } from "@/components/agents/tabs/AgentKindTab";
import { DataTable, type Column } from "@/components/DataTable";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import { fileName, hookRows, hookSummaryCounts, type HookRow } from "@/lib/agents/hookRows";
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

  const columns: Column<HookRow>[] = [
    {
      key: "event",
      header: t("agents.hooksTab.cols.event"),
      className: "w-44 align-top",
      cell: (row) => <AgentHookEventCell row={row} />,
    },
    {
      key: "command",
      header: t("agents.hooksTab.cols.command"),
      className: "align-top",
      cell: (row) => (
        <AgentHookCommandCell
          row={row}
          agentType={agent.type}
          onCheckAgain={() => void hooks.refetch()}
          checking={hooks.isFetching}
        />
      ),
    },
    {
      key: "file",
      header: t("agents.hooksTab.cols.file"),
      className: "align-top",
      cell: (row) => (
        <span className="flex flex-col gap-0.5 text-xs">
          <span className="break-all text-text">
            {row.plugin
              ? `${row.plugin.split("@")[0]} · ${fileName(row.path)}`
              : abbreviateHomePath(row.path)}
          </span>
          <span className="text-text-muted">
            {t("agents.hooksTab.matcher", {
              matcher: row.matcher || t("agents.hooksTab.matcherAny"),
            })}
          </span>
        </span>
      ),
    },
    {
      key: "state",
      header: t("agents.hooksTab.cols.state"),
      className: "w-32 align-top",
      cell: (row) => <AgentHookStateCell row={row} />,
    },
    {
      key: "owner",
      header: t("agents.hooksTab.cols.owner"),
      className: "w-32 align-top",
      cell: (row) => (
        <span className="text-xs text-text-muted">{t(`agents.kindTab.owner.${row.owner}`)}</span>
      ),
    },
    {
      key: "actions",
      header: "",
      className: "text-right align-top",
      cell: (row) => <AgentHookRowActions row={row} onRepair={onRepair} />,
    },
  ];

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
          <DataTable
            rows={visible}
            columns={columns}
            rowKey={(row) => row.key}
            isLoading={hooks.isPending}
            emptyMessage={t("agents.hooksTab.noMatches")}
          />
        )}
      </AgentKindTab>
    </div>
  );
}
