// src/components/agents/AgentPluginsTab.tsx — the agent's Plugins tab: every installed plugin as one list.
//
// Boards 2.1.31–2.1.33, 2.1.60. Spec agent-registry "List an agent's installed
// plugins without writing anything", "Toggle a plugin through the documented
// location only" and "Uninstall a plugin by the type's own strategy". Coffer
// installs no plugins, so every row is the agent's own: a name (opens the info
// dialog), a description · version · marketplace line, a state word only when
// something is wrong (Cache missing), the enabled switch and a ⋯ menu holding
// Uninstall… — disabled, with the reason, while Uninstall cannot run because
// the agent's program is not found (the list then says so, with the hand-off
// to have an agent reinstall it).
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";

import { HelpTip } from "@/components/HelpTip";
import { PluginInfoDialog } from "@/components/agents/PluginInfoDialog";
import { PluginUninstallDialog } from "@/components/agents/PluginUninstallDialog";
import { AgentKindTab } from "@/components/agents/tabs/AgentKindTab";
import { Dot, KindRow } from "@/components/agents/tabs/KindRow";
import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { StatusWord } from "@/components/status/StatusWord";
import { Switch } from "@/components/ui/switch";
import { ActionMenu } from "@/components/ui/menu";
import { agentTypeLabel } from "@/lib/agents/display";
import type { AgentOut } from "@/lib/api/agents";
import type { PluginOut } from "@/lib/api/agents-workspace";
import { useAgentPlugins, useTogglePlugin, useUninstallPlugin } from "@/lib/hooks/useAgents";

const searchText = (p: PluginOut) => p.name;

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
            <AgentHandoff size="sm" help={false} prompt={agent.install_handoff.prompt} />
          ) : null}
        </div>
      ) : null}
    </>
  );

  return (
    <div className="flex max-w-[1000px] flex-col gap-3">
      <AgentKindTab
        rows={rows}
        searchPlaceholder={t("agents.pluginsTab.search")}
        searchText={searchText}
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
        notice={parseErrors.length > 0 || programMissing ? notices : undefined}
      >
        {(visible) =>
          visible.map((p) => (
            <KindRow
              key={p.id}
              name={
                <button
                  type="button"
                  onClick={() => setInfoId(p.id)}
                  className="max-w-full truncate text-left hover:underline"
                >
                  {p.name}
                </button>
              }
              sub={
                <>
                  {p.description ? <span>{p.description}</span> : null}
                  {p.description ? <Dot /> : null}
                  <span className="font-mono">{p.version ?? t("common.emptyValue")}</span>
                  <Dot />
                  <span>{p.marketplace}</span>
                </>
              }
              trailing={
                <>
                  {p.cache_present === false ? (
                    <StatusWord tone="warn">{t("agents.pluginsTab.cacheMissing")}</StatusWord>
                  ) : null}
                  <Switch
                    checked={p.enabled}
                    disabled={toggle.isPending}
                    onCheckedChange={(checked) => toggle.mutate({ id: p.id, enabled: checked })}
                    aria-label={t("agents.pluginsTab.enabledAria", { name: p.name })}
                  />
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
                </>
              }
            />
          ))
        }
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
