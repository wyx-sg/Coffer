// frontend/src/components/agents/AgentMcpControls.tsx — spec 004 v2.
// Compact Coffer-MCP install controls: a single button for the agent detail
// header, and a status badge for the agents table column. Both read the
// (auto-detected) install status from the agent's MCP config.
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import { useAgentMcpInstall, useAgentMcpStatus } from "@/lib/hooks/useAgents";

/**
 * A single install/uninstall button — the label reflects current state.
 * Mutation failures (e.g. the shim binary cannot be resolved) are surfaced
 * inline beneath the button so a click never looks like a silent no-op.
 */
export function AgentMcpButton({ name }: { name: string }) {
  const { t } = useTranslation();
  const status = useAgentMcpStatus(name);
  const mutate = useAgentMcpInstall(name);
  const installed = status.data?.installed ?? false;
  return (
    <div className="flex flex-col items-end gap-1">
      <Button
        variant={installed ? "outline" : "default"}
        size="sm"
        disabled={mutate.isPending || status.isPending}
        onClick={() => mutate.mutate(!installed)}
      >
        {mutate.isPending
          ? t("common.saving")
          : installed
            ? t("agents.mcp.uninstall")
            : t("agents.mcp.install")}
      </Button>
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
