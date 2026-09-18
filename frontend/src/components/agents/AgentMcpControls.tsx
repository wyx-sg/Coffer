// frontend/src/components/agents/AgentMcpControls.tsx — spec agent-registry v2.
// Compact Coffer-MCP install control for the detail-page header: an "Install
// Coffer MCP" button when not installed, an "Uninstall Coffer MCP" button
// (behind a confirm — it cuts the agent off from the gateway) once installed.
// Either outcome is confirmed with a toast; failures toast from the hook. Plus
// a status badge for at-a-glance use in the agents table. Both read the
// (auto-detected) install status from the agent's MCP config.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Plug, Unplug } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { useAgentMcpInstall, useAgentMcpStatus } from "@/lib/hooks/useAgents";

export function AgentMcpButton({ uid }: { uid: string }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const status = useAgentMcpStatus(uid);
  const mutate = useAgentMcpInstall(uid);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const installed = status.data?.installed ?? false;

  const run = (install: boolean) =>
    mutate.mutate(install, {
      onSuccess: () => {
        setConfirmOpen(false);
        toast.success(t(install ? "agents.mcp.installedToast" : "agents.mcp.uninstalledToast"));
      },
    });

  return (
    <>
      {installed ? (
        <Button
          variant="outline"
          size="sm"
          disabled={mutate.isPending}
          onClick={() => setConfirmOpen(true)}
        >
          <Unplug className="mr-1.5 size-3.5" />
          {mutate.isPending ? t("common.saving") : t("agents.mcp.uninstall")}
        </Button>
      ) : (
        <Button size="sm" disabled={mutate.isPending || status.isPending} onClick={() => run(true)}>
          <Plug className="mr-1.5 size-3.5" />
          {mutate.isPending ? t("common.saving") : t("agents.mcp.install")}
        </Button>
      )}
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={t("agents.mcp.uninstallConfirm.title")}
        description={t("agents.mcp.uninstallConfirm.body")}
        confirmLabel={mutate.isPending ? t("common.saving") : t("agents.mcp.uninstall")}
        pending={mutate.isPending}
        onConfirm={() => run(false)}
      />
    </>
  );
}

/** At-a-glance install status for the agents-table "Coffer MCP" column. */
export function AgentMcpStatusBadge({ uid }: { uid: string }) {
  const { t } = useTranslation();
  const status = useAgentMcpStatus(uid);
  if (status.isPending) {
    return <Skeleton className="h-5 w-20" aria-label={t("agents.mcp.checking")} />;
  }
  const installed = status.data?.installed ?? false;
  return (
    <Badge variant={installed ? "secondary" : "outline"}>
      {installed ? t("agents.mcp.installed") : t("agents.mcp.notInstalled")}
    </Badge>
  );
}
