// src/components/agents/AgentPluginsTab.tsx — the agent's Plugins tab: every installed plugin in one table.
//
// Spec agent-registry "List an agent's installed plugins without writing
// anything", "Toggle a plugin through the documented location only", "Uninstall
// a plugin by the type's own strategy" and "Filter an agent's installed kinds by
// owner". Coffer installs no plugins, so every row is the agent's own. A row
// carries the plugin's version, marketplace and state, an enabled switch and
// Uninstall (hidden when the listing says it cannot run now); its name opens a
// dialog saying what the plugin is and which skills, commands, subagents, hooks
// and MCP servers it provides — rows do not expand. When Uninstall cannot run because
// Claude Code's program is not found, the tab offers the agent's reinstall
// hand-off beside saying so.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { PackageMinus, Puzzle } from "lucide-react";

import { PluginInfoDialog } from "@/components/agents/PluginInfoDialog";
import { PluginUninstallDialog } from "@/components/agents/PluginUninstallDialog";
import { TruncatedText } from "@/components/ui/truncated-text";
import { AgentKindTab } from "@/components/agents/tabs/AgentKindTab";
import { DataTable, type Column } from "@/components/DataTable";
import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { StatusWord } from "@/components/status/StatusWord";
import { TableActionButton } from "@/components/table/TableActionButton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Switch } from "@/components/ui/switch";
import { agentTypeLabel } from "@/lib/agents/display";
import type { Owner } from "@/lib/agents/owner";
import type { AgentOut } from "@/lib/api/agents";
import type { PluginOut } from "@/lib/api/agents-workspace";
import { useAgentPlugins, useTogglePlugin, useUninstallPlugin } from "@/lib/hooks/useAgents";

type PluginRow = PluginOut & { owner: Owner };

const searchText = (p: PluginRow) => `${p.name} ${p.id} ${p.marketplace} ${p.description ?? ""}`;

export function AgentPluginsTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const plugins = useAgentPlugins(agent.uid);
  const toggle = useTogglePlugin(agent.uid);
  const uninstall = useUninstallPlugin(agent.uid);
  const [target, setTarget] = useState<PluginOut | null>(null);
  const [infoId, setInfoId] = useState<string | null>(null);

  const rows = useMemo<PluginRow[]>(
    () => (plugins.data?.items ?? []).map((p) => ({ ...p, owner: "own" })),
    [plugins.data],
  );
  const canUninstall = plugins.data?.can_uninstall ?? false;
  const parseErrors = plugins.data?.parse_errors ?? [];
  const agentName = agentTypeLabel(agent.type);
  const codex = agent.type === "codex";
  const enabled = rows.filter((p) => p.enabled).length;
  const summary = [
    t("agents.pluginsTab.summary.plugins", { count: rows.length }),
    t("agents.pluginsTab.summary.allOwn"),
    t("agents.pluginsTab.summary.enabled", { count: enabled }),
  ].join(" · ");

  const columns: Column<PluginRow>[] = [
    {
      key: "plugin",
      className: "w-[38%]",
      header: t("agents.pluginsTab.cols.plugin"),
      cell: (p) => (
        <span className="flex min-w-0 flex-col gap-0.5">
          <button
            type="button"
            onClick={() => setInfoId(p.id)}
            className="block w-full min-w-0 text-left font-medium text-text underline-offset-2 hover:text-accent-text hover:underline"
          >
            <TruncatedText text={p.name} />
          </button>
          {p.description ? (
            <TruncatedText text={p.description} className="text-xs text-text-muted" />
          ) : null}
        </span>
      ),
    },
    {
      key: "version",
      className: "w-[110px]",
      header: t("agents.pluginsTab.cols.version"),
      cell: (p) => (
        <TruncatedText
          mono
          text={p.version ?? t("common.emptyValue")}
          className="text-xs text-text-muted"
        />
      ),
    },
    {
      key: "marketplace",
      className: "w-[22%]",
      header: t("agents.pluginsTab.cols.marketplace"),
      cell: (p) => <TruncatedText text={p.marketplace} className="text-xs text-text-muted" />,
    },
    {
      key: "state",
      className: "w-[110px]",
      header: t("agents.pluginsTab.cols.state"),
      cell: (p) =>
        p.cache_present === false ? (
          <StatusWord tone="warn">{t("agents.pluginsTab.cacheMissing")}</StatusWord>
        ) : (
          <StatusWord tone={p.enabled ? "ok" : "off"}>
            {p.enabled ? t("common.enabled") : t("common.disabled")}
          </StatusWord>
        ),
    },
    {
      key: "actions",
      header: "",
      className: "w-[110px] text-right",
      cell: (p) => (
        <span className="inline-flex items-center justify-end gap-3">
          <Switch
            checked={p.enabled}
            disabled={toggle.isPending}
            onCheckedChange={(checked) => toggle.mutate({ id: p.id, enabled: checked })}
            aria-label={t("agents.pluginsTab.enabledAria", { name: p.name })}
          />
          {canUninstall ? (
            <TableActionButton
              icon={PackageMinus}
              label={t("agents.pluginsTab.uninstall")}
              aria-label={t("agents.pluginsTab.uninstallAria", { name: p.name })}
              destructive
              onClick={() => setTarget(p)}
            />
          ) : null}
        </span>
      ),
    },
  ];

  const footnote = codex
    ? t("agents.pluginsTab.footnote.codex")
    : canUninstall || !plugins.data
      ? t("agents.pluginsTab.footnote.claude")
      : t("agents.pluginsTab.footnote.claudeNoCli");

  return (
    <div className="flex flex-col gap-3.5">
      {parseErrors.length > 0 ? (
        <Alert variant="destructive">
          <AlertDescription>
            <ul className="space-y-0.5">
              {parseErrors.map((pe) => (
                <li key={`${pe.source}:${pe.path}`} className="break-all">
                  {t("agents.pluginsTab.parseError", { file: pe.path, error: pe.error })}
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      ) : null}
      {!codex && plugins.data && !canUninstall && agent.install_handoff ? (
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-text-muted">
          <span>{t("agents.pluginsTab.programMissing", { agent: agentName })}</span>
          <AgentHandoff prompt={agent.install_handoff.prompt} size="sm" />
        </div>
      ) : null}
      <AgentKindTab
        rows={rows}
        summary={summary}
        searchPlaceholder={t("agents.pluginsTab.search")}
        searchText={searchText}
        isLoading={plugins.isPending}
        error={plugins.error}
        onRetry={() => void plugins.refetch()}
        empty={{
          icon: Puzzle,
          title: t("agents.pluginsTab.emptyTitle", { agent: agentName }),
          description: t("agents.pluginsTab.emptyBody", { agent: agentName }),
        }}
        footnote={footnote}
      >
        {(visible) => (
          <DataTable
            fixed
            rows={visible}
            columns={columns}
            rowKey={(p) => p.id}
            isLoading={plugins.isPending}
            emptyMessage={t("agents.pluginsTab.noMatches")}
          />
        )}
      </AgentKindTab>
      <PluginInfoDialog agentUid={agent.uid} pluginId={infoId} onClose={() => setInfoId(null)} />
      <PluginUninstallDialog
        agentType={agent.type}
        plugin={target}
        onClose={() => setTarget(null)}
        pending={uninstall.isPending}
        onConfirm={(p) => uninstall.mutate({ id: p.id }, { onSuccess: () => setTarget(null) })}
      />
    </div>
  );
}
