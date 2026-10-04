// src/components/agents/useAgentPluginsBulk.tsx — bulk Enable, Disable and Uninstall over an agent's plugins.
//
// Spec agent-registry "Act on several of an agent's own items at once". Enable
// and Disable need no confirmation and act only on the plugins not yet in that
// state (the toast says how many were already); a failure is listed under the
// bar with Retry for just those. Uninstall… asks first, and is disabled — with
// the reason — while the agent's program is not found.
import { useMemo, useState, type ReactNode } from "react";
import { Trans, useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";

import { BulkFailures } from "@/components/agents/bulk/BulkFailures";
import { useBulkDialog } from "@/components/agents/bulk/useBulkDialog";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { agentsApi } from "@/lib/api/agents";
import type { PluginOut } from "@/lib/api/agents-workspace";
import { agentPluginsKey } from "@/lib/api/queryKeys";
import { useBulkRun, type BulkFailure } from "@/lib/hooks/useBulkRun";
import { joinNames } from "@/lib/skills/names";

interface Options {
  agentUid: string;
  agentType: string;
  /** The agent's product name, for the reason Uninstall is unavailable. */
  agentLabel: string;
  canUninstall: boolean;
}

/** A switch that ran, so Retry sends the same one again. */
interface Failed {
  enabled: boolean;
  failures: BulkFailure<PluginOut>[];
  total: number;
}

export function useAgentPluginsBulk({ agentUid, agentType, agentLabel, canUninstall }: Options) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const invalidate = useMemo(() => [agentPluginsKey(agentUid)], [agentUid]);
  const uninstall = useBulkDialog<PluginOut>(invalidate);
  const toggle = useBulkRun(invalidate);
  const [failed, setFailed] = useState<Failed | null>(null);
  const codex = agentType === "codex";

  const switchTo = async (enabled: boolean, plugins: PluginOut[], skipped: number) => {
    setFailed(null);
    const result = await toggle.run(plugins, (p) =>
      agentsApi.togglePlugin(agentUid, p.id, enabled),
    );
    if (result.failures.length > 0) {
      setFailed({ enabled, failures: result.failures, total: plugins.length });
      return false;
    }
    toast.success(
      t(enabled ? "agents.pluginsTab.bulk.enabled" : "agents.pluginsTab.bulk.disabled", {
        count: plugins.length,
      }) +
        (skipped > 0
          ? ` ${t(enabled ? "agents.pluginsTab.bulk.alreadyOn" : "agents.pluginsTab.bulk.alreadyOff", { count: skipped })}`
          : ""),
    );
    return true;
  };

  const actions = (rows: PluginOut[], clear: () => void): ReactNode => {
    const off = rows.filter((p) => !p.enabled);
    const on = rows.filter((p) => p.enabled);
    const run = (enabled: boolean) => {
      const todo = enabled ? off : on;
      void switchTo(enabled, todo, rows.length - todo.length).then((ok) => {
        if (ok) clear();
      });
    };
    return (
      <>
        <Button
          variant="outline"
          size="sm"
          disabled={off.length === 0 || toggle.isPending}
          title={
            off.length === 0
              ? t("agents.pluginsTab.bulk.alreadyOn", { count: rows.length })
              : undefined
          }
          onClick={() => run(true)}
        >
          {t("agents.pluginsTab.bulk.enable")}
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={on.length === 0 || toggle.isPending}
          title={
            on.length === 0
              ? t("agents.pluginsTab.bulk.alreadyOff", { count: rows.length })
              : undefined
          }
          onClick={() => run(false)}
        >
          {t("agents.pluginsTab.bulk.disable")}
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={!canUninstall}
          title={
            canUninstall
              ? undefined
              : t("agents.pluginsTab.uninstallDisabled", { agent: agentLabel })
          }
          onClick={() => uninstall.start(rows, clear)}
        >
          <Trash2 aria-hidden /> {t("agents.pluginsTab.bulk.uninstall")}
        </Button>
      </>
    );
  };

  const items = uninstall.items ?? [];
  const total = items.length;
  const dialogFailed = uninstall.failures.length;
  const skills = items.reduce((sum, p) => sum + p.skills.length, 0);
  const names = joinNames(
    items.map((p) => p.name),
    i18n.language,
  );

  const dialogs = (
    <ConfirmDialog
      open={uninstall.items !== null}
      onOpenChange={(next) => {
        if (!next) uninstall.close();
      }}
      title={t("agents.pluginsTab.bulk.uninstallTitle", { count: total })}
      confirmLabel={
        dialogFailed > 0
          ? t("agents.pluginsTab.bulk.retry", { count: dialogFailed })
          : t("agents.pluginsTab.bulk.uninstallConfirm", { count: total })
      }
      pendingLabel={t("agents.pluginsTab.bulk.uninstalling")}
      pending={uninstall.isPending}
      onConfirm={() =>
        void uninstall.confirm(
          (p) => agentsApi.uninstallPlugin(agentUid, p.id),
          (count) => toast.success(t("agents.pluginsTab.bulk.uninstalled", { count })),
        )
      }
    >
      <p className="text-sm text-text-muted">
        {names}
        {" — "}
        <Trans
          i18nKey={
            codex
              ? "agents.pluginsTab.uninstallBody.codex"
              : "agents.pluginsTab.uninstallBody.claude"
          }
          components={{ code: <code className="font-mono text-xs text-text" /> }}
        />
        {skills > 0 ? ` ${t("agents.pluginsTab.uninstallBody.skills", { count: skills })}` : ""}
      </p>
      {dialogFailed > 0 ? (
        <BulkFailures
          title={t("agents.pluginsTab.bulk.uninstallPartial", {
            ok: total - dialogFailed,
            total,
          })}
          failures={uninstall.failures}
          nameOf={(p) => p.name}
        />
      ) : null}
    </ConfirmDialog>
  );

  const notice = failed ? (
    <div className="flex flex-col items-start gap-2">
      <BulkFailures
        title={t(
          failed.enabled
            ? "agents.pluginsTab.bulk.enablePartial"
            : "agents.pluginsTab.bulk.disablePartial",
          { ok: failed.total - failed.failures.length, total: failed.total },
        )}
        failures={failed.failures}
        nameOf={(p) => p.name}
      />
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          loading={toggle.isPending}
          onClick={() =>
            void switchTo(
              failed.enabled,
              failed.failures.map((f) => f.item),
              0,
            )
          }
        >
          {t("agents.pluginsTab.bulk.retry", { count: failed.failures.length })}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setFailed(null)}>
          {t("common.dismiss")}
        </Button>
      </div>
    </div>
  ) : undefined;

  return { actions, dialogs, notice };
}
