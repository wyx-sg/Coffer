// frontend/src/components/agents/AgentPluginsTab.tsx
// "Plugins" tab on the agent detail page. Shows ALL installed plugins for the
// agent in a single table — the marketplace each plugin came from is a column,
// not a per-marketplace section — so it reads like the other resource surfaces.
// Each row has name, marketplace (+ source), an enabled Switch, a cache-status
// badge, and an uninstall action (codex only — claude_code agents must use the
// `claude plugin` CLI to uninstall).
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { PluginDetailRow } from "@/components/agents/AgentPluginDetail";
import { DataTable, type Column } from "@/components/DataTable";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
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
import { useAgentPlugins, useTogglePlugin, useUninstallPlugin } from "@/lib/hooks/useAgents";

export function AgentPluginsTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const plugins = useAgentPlugins(agent.name);
  const toggle = useTogglePlugin(agent.name);
  const uninstall = useUninstallPlugin(agent.name);
  const [uninstallTarget, setUninstallTarget] = useState<PluginOut | null>(null);

  const items = plugins.data?.items ?? [];
  const marketplaces = plugins.data?.marketplaces ?? [];
  const parseErrors = plugins.data?.parse_errors ?? [];
  // Show the uninstall button on the agent's reported capability (Codex edits
  // its config; Claude shells out to `claude plugin uninstall` when present),
  // not on the agent type. When unavailable, keep the "use the CLI" hint.
  const canUninstall = plugins.data?.can_uninstall ?? false;

  // marketplace name → source (e.g. "jarrodwatts/claude-hud"), so the
  // marketplace column can show the origin alongside the name.
  const sourceOf = new Map(marketplaces.map((m) => [m.name, m.source ?? ""]));

  const columns: Column<PluginOut>[] = [
    {
      key: "name",
      header: t("resources.cols.name"),
      className: "whitespace-nowrap",
      cell: (p) => <span className="font-medium">{p.name}</span>,
    },
    {
      key: "marketplace",
      header: t("agents.workspace.pluginsTab.marketplace"),
      cell: (p) => {
        const source = sourceOf.get(p.marketplace);
        return (
          <span className="flex items-center gap-2">
            <span>{p.marketplace}</span>
            {source ? (
              <span className="font-mono text-xs text-muted-foreground">({source})</span>
            ) : null}
          </span>
        );
      },
    },
    {
      key: "enabled",
      header: t("agents.workspace.pluginsTab.enabled"),
      className: "whitespace-nowrap",
      cell: (p) => (
        <Switch
          checked={p.enabled}
          disabled={toggle.isPending}
          onClick={(e) => e.stopPropagation()}
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
        canUninstall ? (
          <Button
            size="sm"
            variant="outline"
            className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
            onClick={(e) => {
              e.stopPropagation();
              setUninstallTarget(p);
            }}
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

      <Card className="space-y-3 p-4">
        {plugins.isPending ? (
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : plugins.error ? (
          <p className="text-sm text-destructive">{translateApiError(t, plugins.error)}</p>
        ) : (
          <DataTable
            rows={items}
            columns={columns}
            rowKey={(p) => p.id}
            search={{
              accessor: (p) => `${p.name} ${p.marketplace} ${sourceOf.get(p.marketplace) ?? ""}`,
              placeholder: t("agents.workspace.pluginsTab.searchPlaceholder"),
            }}
            getRowDetail={(p) => <PluginDetailRow plugin={p} />}
            emptyMessage={t("agents.workspace.pluginsTab.empty")}
          />
        )}
      </Card>

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
