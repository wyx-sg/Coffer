// src/components/agents/list/AgentPendingStatus.tsx — an agent's status while long work runs on it.
//
// Replaces the state word with a spinner and what is happening ("Disconnecting…"),
// so a row whose config files are being written never looks frozen.
import { useTranslation } from "react-i18next";

import { Spinner } from "@/components/ui/spinner";
import type { AgentPending } from "@/lib/hooks/useAgentPending";

export function AgentPendingStatus({ pending }: { pending: AgentPending }) {
  const { t } = useTranslation();
  return (
    <span
      role="status"
      className="inline-flex items-center gap-[7px] whitespace-nowrap text-xs text-text-muted"
    >
      <Spinner />
      {t(`agents.pending.${pending}`)}
    </span>
  );
}
