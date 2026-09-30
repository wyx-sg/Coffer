// src/components/agents/AgentHookUntrustedPanel.tsx — Codex has not approved Coffer's hook, under its row (board 2.1.51).
//
// Codex runs a new or changed hook only after the user approves it in `/hooks`;
// until then it skips Coffer's hook and every session starts without memory.
// Coffer never approves it for the user, so the panel says how, hands over the
// slash command, and re-reads the hook once they have.
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { CopyHooksButton } from "@/components/agents/CopyHooksButton";
import { TableActionButton } from "@/components/table/TableActionButton";
import { agentTypeLabel } from "@/lib/agents/display";

interface Props {
  agentType: string;
  onCheckAgain: () => void;
  checking: boolean;
}

export function AgentHookUntrustedPanel({ agentType, onCheckAgain, checking }: Props) {
  const { t } = useTranslation();
  const agent = agentTypeLabel(agentType);
  return (
    <div className="mt-2 flex flex-col gap-2 rounded-md border border-border-subtle bg-surface-sunken p-3 font-sans">
      <p className="text-xs font-medium text-text">
        {t("agents.hooksTab.untrusted.title", { agent })}
      </p>
      <p className="text-xs text-text-muted">{t("agents.hooksTab.untrusted.body", { agent })}</p>
      <span className="flex flex-wrap gap-2">
        <TableActionButton
          icon={RefreshCw}
          label={t("agents.hooksTab.neverFired.checkAgain")}
          disabled={checking}
          onClick={onCheckAgain}
        />
        <CopyHooksButton />
      </span>
    </div>
  );
}
