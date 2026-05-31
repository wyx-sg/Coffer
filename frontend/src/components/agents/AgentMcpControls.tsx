// frontend/src/components/agents/AgentMcpControls.tsx — spec 004 v2.
// Compact Coffer-MCP install control: an "Install Coffer MCP" button when not
// installed, and a plain "Coffer MCP installed" status (no uninstall action)
// once installed. Plus a status badge for at-a-glance use elsewhere. Both read
// the (auto-detected) install status from the agent's MCP config.
import { useTranslation } from "react-i18next";
import { Plug, Unplug } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import { useAgentMcpInstall, useAgentMcpStatus } from "@/lib/hooks/useAgents";

/**
 * Coffer-MCP control. When not installed: an "Install Coffer MCP" button; when
 * installed: an "Uninstall Coffer MCP" button (icon+text, matching the other
 * header actions). Mutation failures (e.g. the shim binary cannot be resolved)
 * are surfaced inline so a click never looks like a silent no-op.
 */
export function AgentMcpButton({ name }: { name: string }) {
  const { t } = useTranslation();
  const status = useAgentMcpStatus(name);
  const mutate = useAgentMcpInstall(name);
  const installed = status.data?.installed ?? false;

  return (
    <div className="flex flex-col items-end gap-1.5">
      {installed ? (
        <Button
          variant="outline"
          size="sm"
          disabled={mutate.isPending}
          onClick={() => mutate.mutate(false)}
        >
          <Unplug className="mr-1.5 size-3.5" />
          {mutate.isPending ? t("common.saving") : t("agents.mcp.uninstall")}
        </Button>
      ) : (
        <Button
          size="sm"
          disabled={mutate.isPending || status.isPending}
          onClick={() => mutate.mutate(true)}
        >
          <Plug className="mr-1.5 size-3.5" />
          {mutate.isPending ? t("common.saving") : t("agents.mcp.install")}
        </Button>
      )}
      {mutate.error ? (
        <p className="max-w-xs text-right text-xs text-destructive">
          {translateApiError(t, mutate.error)}
        </p>
      ) : null}
    </div>
  );
}

/** At-a-glance install status for the agents-table "Coffer MCP" column. */
export function AgentMcpStatusBadge({ name }: { name: string }) {
  const { t } = useTranslation();
  const status = useAgentMcpStatus(name);
  if (status.isPending) {
    return <span className="text-xs text-muted-foreground">…</span>;
  }
  const installed = status.data?.installed ?? false;
  return (
    <Badge variant={installed ? "secondary" : "outline"}>
      {installed ? t("agents.mcp.installed") : t("agents.mcp.notInstalled")}
    </Badge>
  );
}
