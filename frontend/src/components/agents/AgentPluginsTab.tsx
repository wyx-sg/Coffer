// src/components/agents/AgentPluginsTab.tsx — the agent's Plugins tab: every installed plugin as one list.
//
// Boards 2.1.31–2.1.33, 2.1.60. Spec agent-registry "List an agent's installed
// plugins without writing anything", "Toggle a plugin through the documented
// location only" and "Uninstall a plugin by the type's own strategy". Coffer
// installs no plugins, so every row is the agent's own, one table row: Name
// (opens the info dialog), Description, Version, Marketplace, Enabled (a state
// word only when something is wrong — Cache missing — and the switch), then a ⋯ menu holding
// Uninstall… — disabled, with the reason, while Uninstall cannot run because
// the agent's program is not found (the list then says so, with the hand-off
// to have an agent reinstall it).
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";

import { HelpTip } from "@/components/HelpTip";
import { PluginInfoDialog } from "@/components/agents/PluginInfoDialog";
import { useAgentPluginsBulk } from "@/components/agents/useAgentPluginsBulk";
import { PluginUninstallDialog } from "@/components/agents/PluginUninstallDialog";
import { AgentKindTab, type KindColumn } from "@/components/agents/tabs/AgentKindTab";
import { KindActions, KindName, KindRow } from "@/components/agents/tabs/KindRow";
import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { StatusWord } from "@/components/status/StatusWord";
import { Switch } from "@/components/ui/switch";
import { ActionMenu } from "@/components/ui/menu";
import { TruncatedText } from "@/components/ui/truncated-text";
import { agentTypeLabel } from "@/lib/agents/display";
import type { AgentOut } from "@/lib/api/agents";
import type { PluginOut } from "@/lib/api/agents-workspace";
import { useAgentPlugins, useTogglePlugin, useUninstallPlugin } from "@/lib/hooks/useAgents";

const searchText = (p: PluginOut) => p.name;

function pluginColumns(t: (key: string) => string): KindColumn[] {
  return [
    { key: "name", header: t("agents.pluginsTab.cols.name"), className: "w-[20%]" },
    { key: "description", header: t("agents.pluginsTab.cols.description") },
    { key: "version", header: t("agents.pluginsTab.cols.version"), className: "w-[14%]" },
    { key: "marketplace", header: t("agents.pluginsTab.cols.marketplace"), className: "w-[17%]" },
    { key: "enabled", header: t("agents.pluginsTab.cols.enabled"), className: "w-36 text-right" },
    { key: "actions", className: "w-12" },
  ];
}

export function AgentPluginsTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const plugins = useAgentPlugins(agent.uid);
  const toggle = useTogglePlugin(agent.uid);
  const uninstall = useUninstallPlugin(agent.uid);
  const [target, setTarget] = useState<PluginOut | null>(null);
  const [infoId, setInfoId] = useState<string | null>(null);

  const rows = useMemo<PluginOut[]>(() => plugins.data?.items ?? [], [plugins.data]);
  const canUninstall = plugins.data?.can_uninstall ?? false;
  const parseErrors = plugins.data?.parse_errors ?? [];
  const agentName = agentTypeLabel(agent.type);
  const codex = agent.type === "codex";
  const programMissing = Boolean(plugins.data) && !codex && !canUninstall;

  const bulk = useAgentPluginsBulk({
    agentUid: agent.uid,
    agentType: agent.type,
    agentLabel: agentName,
    canUninstall,
  });

  const notices = (
    <>
      {parseErrors.map((pe) => (
        <p
          key={`${pe.source}:${pe.path}`}
          role="alert"
          className="flex items-start gap-2 break-all text-sm text-text"
        >
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
          {t("agents.pluginsTab.parseError", { file: pe.path, error: pe.error })}
        </p>
      ))}
      {programMissing ? (
        <div className="flex flex-wrap items-center gap-3 text-sm text-text">
          <AlertTriangle className="size-4 shrink-0 text-warning" aria-hidden />
          <span className="min-w-0 flex-1">
            {t("agents.pluginsTab.programMissing", { agent: agentName })}
          </span>
          {agent.install_handoff ? (
            <AgentHandoff size="sm" prompt={agent.install_handoff.prompt} />
          ) : null}
        </div>
      ) : null}
      {bulk.notice}
    </>
  );

  return (
    <div className="flex max-w-[1000px] flex-col gap-3">
      <AgentKindTab
        rows={rows}
        searchPlaceholder={t("agents.pluginsTab.search")}
        searchText={searchText}
        columns={pluginColumns(t)}
        isLoading={plugins.isPending}
        error={plugins.error}
        onRetry={() => void plugins.refetch()}
        empty={{
          title: t("agents.pluginsTab.emptyTitle", { agent: agentName }),
          description: t("agents.pluginsTab.emptyBody", { agent: agentName }),
        }}
        noMatch={t("agents.pluginsTab.noMatches")}
        searchAside={
          <HelpTip label={t("agents.pluginsTab.aboutAria")}>
            <p className="text-xs">
              {t(codex ? "agents.pluginsTab.help.codex" : "agents.pluginsTab.help.claude")}
            </p>
          </HelpTip>
        }
        notice={parseErrors.length > 0 || programMissing || bulk.notice ? notices : undefined}
        bulk={{
          rowKey: (p) => p.id,
          barLabel: t("agents.pluginsTab.bulk.label"),
          actions: bulk.actions,
        }}
      >
        {(visible, select) =>
          visible.map((p) => (
            <KindRow
              key={p.id}
              leading={select.leading(p, p.name)}
              cells={[
                <KindName key="name">
                  <button
                    type="button"
                    onClick={() => setInfoId(p.id)}
                    className="max-w-full truncate text-left hover:underline"
                  >
                    {p.name}
                  </button>
                </KindName>,
                p.description ? (
                  <TruncatedText key="description" text={p.description} />
                ) : (
                  <span key="description" className="text-text-subtle">
                    {t("common.emptyValue")}
                  </span>
                ),
                <TruncatedText key="version" mono text={p.version ?? t("common.emptyValue")} />,
                <TruncatedText key="marketplace" text={p.marketplace} />,
                <KindActions key="enabled">
                  {p.cache_present === false ? (
                    <StatusWord tone="warn">{t("agents.pluginsTab.cacheMissing")}</StatusWord>
                  ) : null}
                  <Switch
                    checked={p.enabled}
                    disabled={toggle.isPending}
                    onCheckedChange={(checked) => toggle.mutate({ id: p.id, enabled: checked })}
                    aria-label={t("agents.pluginsTab.enabledAria", { name: p.name })}
                  />
                </KindActions>,
                <KindActions key="actions">
                  <ActionMenu
                    label={t("agents.kindTab.moreFor", { name: p.name })}
                    actions={[
                      {
                        key: "uninstall",
                        label: t("agents.pluginsTab.menu.uninstall"),
                        description: canUninstall
                          ? undefined
                          : t("agents.pluginsTab.uninstallDisabled", { agent: agentName }),
                        destructive: true,
                        disabled: !canUninstall,
                        onSelect: () => setTarget(p),
                      },
                    ]}
                  />
                </KindActions>,
              ]}
            />
          ))
        }
      </AgentKindTab>
      {bulk.dialogs}
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
