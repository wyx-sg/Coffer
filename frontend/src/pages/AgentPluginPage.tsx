// frontend/src/pages/AgentPluginPage.tsx — spec agent-registry
// "Read one installed plugin's detail read-only" and "Expose every agent
// operation through REST, CLI and the Agents page".
// One of the agent's installed plugins, reached by clicking its name on the
// Plugins tab: the manifest metadata, where it came from and where it is
// installed, and everything its package contributes. The two writes the tab
// offers — the enabled switch and uninstall — sit in the header; a successful
// uninstall returns to the Plugins tab, since the page's subject is gone.
//
// The plugin is addressed by its `<name>@<marketplace>` id in the path,
// URL-encoded (the `@` and any `/` survive as one segment); the router hands
// the decoded id back.
import { useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Puzzle, Trash2 } from "lucide-react";

import { PluginContentsCard, PluginOverviewCard } from "@/components/agents/AgentPluginSections";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import { useAgentPlugin, useTogglePlugin, useUninstallPlugin } from "@/lib/hooks/useAgents";

export function AgentPluginPage() {
  const { t } = useTranslation();
  const { uid = "", pluginId = "" } = useParams<{ uid: string; pluginId: string }>();
  const navigate = useNavigate();
  // The Plugins tab passes its own location as the return target (mirrors
  // SkillDetailPage); a page opened from a bookmark falls back to the same tab.
  const backState = useLocation().state as { backTo?: string; backLabel?: string } | null;
  const back = {
    to: backState?.backTo ?? `/agents/${encodeURIComponent(uid)}?tab=plugins`,
    label: t("common.backTo", {
      label: backState?.backLabel ?? t("agents.workspace.plugins"),
    }),
  };
  const { data, isPending, error } = useAgentPlugin(uid, pluginId);
  const toggle = useTogglePlugin(uid);
  const uninstall = useUninstallPlugin(uid);
  const [confirmOpen, setConfirmOpen] = useState(false);

  if (isPending) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-muted-foreground">
          {t("common.loading")}
        </CardContent>
      </Card>
    );
  }
  if (error || !data) {
    return (
      <EmptyState
        icon={Puzzle}
        title={t("agents.pluginDetail.loadFailed")}
        description={error ? translateApiError(t, error) : undefined}
        action={
          <Button variant="outline" asChild>
            <Link to={back.to}>
              <ArrowLeft className="mr-1 size-4" />
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
          <>
            <Badge variant="secondary">{p.marketplace}</Badge>
            {p.cache_present === false ? (
              <Badge variant="destructive">{t("agents.workspace.pluginsTab.cacheMissing")}</Badge>
            ) : null}
          </>
        }
        actions={
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm">
              <Switch
                checked={p.enabled}
                disabled={toggle.isPending}
                onCheckedChange={(checked) => toggle.mutate({ id: p.id, enabled: checked })}
                aria-label={`${t("agents.workspace.pluginsTab.enabled")}: ${p.name}`}
              />
              {t("agents.workspace.pluginsTab.enabled")}
            </label>
            {data.can_uninstall ? (
              <Button
                variant="outline"
                size="sm"
                className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
                onClick={() => setConfirmOpen(true)}
              >
                <Trash2 className="mr-1.5 size-3.5" />
                {t("agents.workspace.pluginsTab.uninstall")}
              </Button>
            ) : (
              <span className="text-xs text-muted-foreground">
                {t("agents.workspace.pluginsTab.claudeUninstallHint")}
              </span>
            )}
          </div>
        }
      />

      <PluginOverviewCard detail={data} />
      <PluginContentsCard detail={data} />

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={t("agents.workspace.pluginsTab.uninstallConfirmTitle", { name: p.name })}
        description={t("agents.workspace.pluginsTab.uninstallConfirm")}
        confirmLabel={t("agents.workspace.pluginsTab.uninstall")}
        pending={uninstall.isPending}
        onConfirm={() =>
          uninstall.mutate(
            { id: p.id },
            {
              onSuccess: () => {
                setConfirmOpen(false);
                navigate(back.to);
              },
            },
          )
        }
      />
    </div>
  );
}
