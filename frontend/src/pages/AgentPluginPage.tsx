// src/pages/AgentPluginPage.tsx — one of the agent's installed plugins, opened from its Plugins tab.
//
// Spec agent-registry "Read one installed plugin's detail read-only" and
// "Expose every agent operation through REST, CLI and the Agents page": the
// manifest metadata, where the plugin came from and where it is installed, and
// everything its package contributes. The two writes the tab offers — the
// enabled switch and Uninstall — sit in the header; a successful uninstall
// returns to the Plugins tab, since the page's subject is gone, and so does the
// back link. Addressed as `/agents/<type>/plugins/<name>@<marketplace>`, the id
// URL-encoded as one segment; the router hands it back decoded.
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, PackageMinus, Puzzle } from "lucide-react";

import { PluginContentsCard, PluginOverviewCard } from "@/components/agents/AgentPluginSections";
import { PluginUninstallDialog } from "@/components/agents/PluginUninstallDialog";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { agentTabPath } from "@/lib/agents/routes";
import type { PluginOut } from "@/lib/api/agents";
import { translateApiError } from "@/lib/api/errors";
import { useAgentRoute } from "@/lib/hooks/useAgentRoute";
import { useAgentPlugin, useTogglePlugin, useUninstallPlugin } from "@/lib/hooks/useAgents";

export function AgentPluginPage() {
  const { t } = useTranslation();
  const { pluginId = "" } = useParams<{ pluginId: string }>();
  const navigate = useNavigate();
  const route = useAgentRoute();
  const type = route.type ?? "";
  const back = {
    to: agentTabPath(type, "plugins"),
    label: t("common.backTo", { label: t("agents.workspace.plugins") }),
  };
  const { data, isPending, error } = useAgentPlugin(route.uid, pluginId);
  const toggle = useTogglePlugin(route.uid);
  const uninstall = useUninstallPlugin(route.uid);
  const [target, setTarget] = useState<PluginOut | null>(null);

  if (route.isPending || (route.uid && isPending)) {
    return (
      <div className="space-y-4" aria-busy="true" aria-label={t("common.loading")}>
        <Skeleton className="h-10 w-1/3" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  const failure = route.error ?? error;
  if (failure || !data) {
    return (
      <EmptyState
        icon={Puzzle}
        tone={failure ? "error" : "default"}
        title={t("agents.pluginDetail.loadFailed")}
        description={failure ? translateApiError(t, failure) : undefined}
        action={
          <Button variant="outline" asChild>
            <Link to={back.to}>
              <ArrowLeft className="mr-1 size-4" aria-hidden />
              {back.label}
            </Link>
          </Button>
        }
      />
    );
  }

  const p = data.plugin;
  return (
    <div className="space-y-6">
      <PageHeader
        back={back}
        title={p.name}
        subtitle={<span className="font-mono text-xs">{p.id}</span>}
        badges={
          p.cache_present === false ? (
            <StatusWord tone="warn">{t("agents.pluginsTab.cacheMissing")}</StatusWord>
          ) : null
        }
        actions={
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm">
              <Switch
                checked={p.enabled}
                disabled={toggle.isPending}
                onCheckedChange={(checked) => toggle.mutate({ id: p.id, enabled: checked })}
                aria-label={t("agents.pluginsTab.enabledAria", { name: p.name })}
              />
              {t("common.enabled")}
            </label>
            {data.can_uninstall ? (
              <Button
                variant="outline"
                size="sm"
                className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
                onClick={() => setTarget(p)}
              >
                <PackageMinus className="mr-1.5 size-3.5" aria-hidden />
                {t("agents.pluginsTab.uninstall")}
              </Button>
            ) : (
              <span className="text-xs text-text-muted">
                {t("agents.pluginsTab.footnote.claudeNoCli")}
              </span>
            )}
          </div>
        }
      />

      <PluginOverviewCard detail={data} />
      <PluginContentsCard detail={data} />

      <PluginUninstallDialog
        agentType={type}
        plugin={target}
        onClose={() => setTarget(null)}
        pending={uninstall.isPending}
        onConfirm={(plugin) =>
          uninstall.mutate(
            { id: plugin.id },
            {
              onSuccess: () => {
                setTarget(null);
                navigate(back.to);
              },
            },
          )
        }
      />
    </div>
  );
}
