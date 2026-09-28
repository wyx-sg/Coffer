// frontend/src/components/agents/AgentPluginsBulkActions.tsx
// Bulk actions for the agent's plugins table: enable / disable / uninstall over
// the selected rows. Enable/disable fan out toggle calls with allSettled (via
// useBulkMutate). Uninstall is destructive — only offered when the agent can
// uninstall (Codex / Claude with the CLI present) — and owns its own confirm
// dialog. Kept in its own file to bound AgentPluginsTab.tsx.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PackageMinus, Power, PowerOff } from "lucide-react";

import { TableActionButton } from "@/components/table/TableActionButton";
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
import { agentPluginsKey } from "@/lib/api/queryKeys";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";

export function AgentPluginsBulkActions({
  agentUid,
  rows,
  clear,
  canUninstall,
}: {
  agentUid: string;
  rows: PluginOut[];
  clear: () => void;
  canUninstall: boolean;
}) {
  const { t } = useTranslation();
  const [confirmUninstall, setConfirmUninstall] = useState(false);
  const toggle = useBulkMutate({ invalidate: [agentPluginsKey(agentUid)] });
  const uninstall = useBulkMutate({ invalidate: [agentPluginsKey(agentUid)] });

  const setAll = async (enabled: boolean) => {
    await toggle.run(rows, (p) => agentsApi.togglePlugin(agentUid, p.id, enabled));
    clear();
  };

  const uninstallAll = async () => {
    await uninstall.run(rows, (p) => agentsApi.uninstallPlugin(agentUid, p.id));
    setConfirmUninstall(false);
    clear();
  };

  return (
    <>
      <TableActionButton
        icon={Power}
        label={t("common.bulk.enable")}
        disabled={toggle.isPending}
        onClick={() => void setAll(true)}
      />
      <TableActionButton
        icon={PowerOff}
        label={t("common.bulk.disable")}
        disabled={toggle.isPending}
        onClick={() => void setAll(false)}
      />
      {canUninstall ? (
        <TableActionButton
          icon={PackageMinus}
          label={t("agents.workspace.pluginsTab.uninstall")}
          destructive
          disabled={uninstall.isPending}
          onClick={() => setConfirmUninstall(true)}
        />
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
