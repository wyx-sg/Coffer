// frontend/src/components/agents/AgentPluginsBulkActions.tsx
// Bulk actions for the agent's plugins table: enable / disable / uninstall over
// the selected rows. Enable/disable fan out toggle calls with allSettled (via
// useBulkMutate). Uninstall is destructive — only offered when the agent can
// uninstall (Codex / Claude with the CLI present) — and owns its own confirm
// dialog. Kept in its own file to bound AgentPluginsTab.tsx.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Power, PowerOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { agentsApi, type PluginOut } from "@/lib/api/agents";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";

export function AgentPluginsBulkActions({
  agentName,
  rows,
  clear,
  canUninstall,
}: {
  agentName: string;
  rows: PluginOut[];
  clear: () => void;
  canUninstall: boolean;
}) {
  const { t } = useTranslation();
  const [confirmUninstall, setConfirmUninstall] = useState(false);
  const toggle = useBulkMutate({ invalidate: [["agents", agentName, "plugins"]] });
  const uninstall = useBulkMutate({ invalidate: [["agents", agentName, "plugins"]] });

  const setAll = async (enabled: boolean) => {
    await toggle.run(rows, (p) => agentsApi.togglePlugin(agentName, p.id, enabled));
    clear();
  };

  const uninstallAll = async () => {
    await uninstall.run(rows, (p) => agentsApi.uninstallPlugin(agentName, p.id));
    setConfirmUninstall(false);
    clear();
  };

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        disabled={toggle.isPending}
        onClick={() => void setAll(true)}
      >
        <Power className="mr-1.5 size-3.5" />
        {t("common.bulk.enable")}
      </Button>
      <Button
        size="sm"
        variant="outline"
        disabled={toggle.isPending}
        onClick={() => void setAll(false)}
      >
        <PowerOff className="mr-1.5 size-3.5" />
        {t("common.bulk.disable")}
      </Button>
      {canUninstall ? (
        <Button
          size="sm"
          variant="outline"
          className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
          disabled={uninstall.isPending}
          onClick={() => setConfirmUninstall(true)}
        >
          {t("agents.workspace.pluginsTab.uninstall")}
        </Button>
      ) : null}

      <Dialog open={confirmUninstall} onOpenChange={setConfirmUninstall}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("agents.workspace.pluginsTab.uninstall")}</DialogTitle>
            <DialogDescription>
              {t("agents.workspace.pluginsTab.bulkUninstallConfirm", { count: rows.length })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmUninstall(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={uninstall.isPending}
              onClick={() => void uninstallAll()}
            >
              {t("agents.workspace.pluginsTab.uninstall")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
