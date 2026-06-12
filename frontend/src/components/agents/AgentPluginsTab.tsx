// frontend/src/components/agents/AgentPluginsTab.tsx
// "Plugins" tab on the agent detail page. Shows the installed plugins for the
// agent, grouped by marketplace. Each row has a name, enabled Switch, cache
// status badge, and an uninstall action (codex only — claude_code agents must
// use the `claude plugin` CLI to uninstall).
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import type { AgentOut, PluginOut } from "@/lib/api/agents";
import {
  useAgentPlugins,
  useTogglePlugin,
  useUninstallPlugin,
} from "@/lib/hooks/useAgents";

export function AgentPluginsTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const plugins = useAgentPlugins(agent.name);
  const toggle = useTogglePlugin(agent.name);
  const uninstall = useUninstallPlugin(agent.name);
  const [uninstallTarget, setUninstallTarget] = useState<PluginOut | null>(null);

  const isCodex = agent.type === "codex";

  const columns: Column<PluginOut>[] = [
    {
      key: "name",
      header: t("resources.cols.name"),
      className: "whitespace-nowrap",
      cell: (p) => <span className="font-medium">{p.name}</span>,
    },
    {
      key: "enabled",
      header: t("agents.workspace.pluginsTab.enabled"),
      className: "whitespace-nowrap",
      cell: (p) => (
        <Switch
          checked={p.enabled}
          disabled={toggle.isPending}
          onCheckedChange={(checked) => toggle.mutate({ id: p.id, enabled: checked })}
          aria-label={`${t("agents.workspace.pluginsTab.enabled")}: ${p.name}`}
        />
      ),
    },
    {
      key: "cache",
      header: "",
      cell: (p) =>
        p.cache_present === false ? (
          <Badge variant="destructive">{t("agents.workspace.pluginsTab.cacheMissing")}</Badge>
        ) : null,
    },
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (p) =>
        isCodex ? (
          <Button
            size="sm"
            variant="outline"
            className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
            onClick={() => setUninstallTarget(p)}
          >
            {t("agents.workspace.pluginsTab.uninstall")}
          </Button>
        ) : (
          <span className="text-xs text-muted-foreground">
            {t("agents.workspace.pluginsTab.claudeUninstallHint")}
          </span>
        ),
    },
  ];

  const items = plugins.data?.items ?? [];
  const marketplaces = plugins.data?.marketplaces ?? [];
  const parseErrors = plugins.data?.parse_errors ?? [];

  // Build a map from marketplace name → source for group headers.
  const marketplaceMap = new Map(marketplaces.map((m) => [m.name, m]));

  // Group items by marketplace.
  const grouped = new Map<string, PluginOut[]>();
  for (const item of items) {
    const list = grouped.get(item.marketplace) ?? [];
    list.push(item);
    grouped.set(item.marketplace, list);
  }

  return (
    <div className="space-y-6">
      {parseErrors.length > 0 && (
        <Alert variant="destructive">
          <AlertDescription>
            <p className="font-medium">{t("agents.workspace.pluginsTab.parseError")}</p>
            <ul className="mt-1 space-y-0.5">
              {(parseErrors as { source: string; path: string; error: string }[]).map((pe) => (
                <li key={`${pe.source}:${pe.path}`} className="font-mono text-xs">
                  {pe.source}: {pe.error}
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      {plugins.isPending ? (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : plugins.error ? (
        <p className="text-sm text-destructive">{translateApiError(t, plugins.error)}</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("agents.workspace.pluginsTab.empty")}</p>
      ) : grouped.size === 0 ? (
        <DataTable
          rows={items}
          columns={columns}
          rowKey={(p) => p.id}
          emptyMessage={t("agents.workspace.pluginsTab.empty")}
        />
      ) : (
        Array.from(grouped.entries()).map(([marketplaceName, rows]) => {
          const mp = marketplaceMap.get(marketplaceName);
          return (
            <section key={marketplaceName} className="space-y-3">
              <h3 className="text-sm font-medium text-muted-foreground">
                {t("agents.workspace.pluginsTab.marketplace")}: {marketplaceName}
                {mp?.source ? (
                  <span className="ml-2 font-mono text-xs">({mp.source})</span>
                ) : null}
              </h3>
              <DataTable
                rows={rows}
                columns={columns}
                rowKey={(p) => p.id}
                emptyMessage={t("agents.workspace.pluginsTab.empty")}
              />
            </section>
          );
        })
      )}

      <Dialog
        open={uninstallTarget !== null}
        onOpenChange={(open) => {
          if (!open) setUninstallTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t("agents.workspace.pluginsTab.uninstall")}: {uninstallTarget?.name}
            </DialogTitle>
            <DialogDescription>
              {t("agents.workspace.pluginsTab.uninstallConfirm")}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setUninstallTarget(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={uninstall.isPending}
              onClick={() => {
                if (!uninstallTarget) return;
                uninstall.mutate(
                  { id: uninstallTarget.id },
                  { onSuccess: () => setUninstallTarget(null) },
                );
              }}
            >
              {t("agents.workspace.pluginsTab.uninstall")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
