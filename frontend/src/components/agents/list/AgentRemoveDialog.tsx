// src/components/agents/list/AgentRemoveDialog.tsx — "Remove <agent> from Coffer?", from a row's menu or its left-behind notice.
//
// Removing takes Coffer's entry and hook out of the agent's config first — the
// delete route drops only the registration, and a connection left behind
// would keep pointing the agent at Coffer — and then removes the agent. The
// agent itself, its config, sessions and memory stay; the row reads Detected,
// not added again. The dialog closes only once both steps succeed.
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import type { AgentTypeOut } from "@/lib/api/agents";
import { useAgentConnect, useAgentConnection, useRemoveAgent } from "@/lib/hooks/useAgents";

interface Props {
  row: AgentTypeOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AgentRemoveDialog({ row, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const uid = row.uid ?? "";
  const connection = useAgentConnection(uid).data;
  const disconnect = useAgentConnect(uid);
  const remove = useRemoveAgent();
  const name = agentTypeLabel(row.type);

  const confirm = async () => {
    if (connection?.parts.some((p) => p.installed)) await disconnect.mutateAsync(false);
    await remove.mutateAsync(uid);
  };

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("agents.removeDialog.title", { name })}
      description={t("agents.removeDialog.body", {
        name,
        dir: abbreviateHomePath(row.config_dir),
      })}
      confirmLabel={t("agents.removeDialog.confirm")}
      errorTitle={t("common.couldntRemove", { name })}
      pending={disconnect.isPending || remove.isPending}
      onConfirm={confirm}
    />
  );
}
