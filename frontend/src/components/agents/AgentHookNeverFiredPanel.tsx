// src/components/agents/AgentHookNeverFiredPanel.tsx — why Coffer's installed hook has never fired, under its row.
//
// A current, trusted hook with no recorded fire means the agent has been
// starting sessions without Coffer's memory. The panel says so, names the likely
// cause for the agent's type, and offers a re-read and the Activity page, where
// every fire is logged.
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Activity, RefreshCw } from "lucide-react";

import { TableActionButton } from "@/components/table/TableActionButton";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";

interface Props {
  agentType: string;
  path: string;
  onCheckAgain: () => void;
  checking: boolean;
}

export function AgentHookNeverFiredPanel({ agentType, path, onCheckAgain, checking }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const params = { agent: agentTypeLabel(agentType), file: abbreviateHomePath(path) };
  const cause = agentType === "codex" ? "codex" : "claude_code";
  return (
    <div className="mt-2 flex flex-col gap-2 rounded-md border border-border-subtle bg-surface-sunken p-3 font-sans">
      <p className="text-xs font-medium text-text">{t("agents.hooksTab.neverFired.title")}</p>
      <p className="text-xs text-text-muted">{t("agents.hooksTab.neverFired.body", params)}</p>
      <p className="text-xs text-text-muted">
        <span className="font-medium text-text">{t("agents.hooksTab.neverFired.causeLabel")}</span>{" "}
        {t(`agents.hooksTab.neverFired.cause.${cause}`, params)}
      </p>
      <span className="flex flex-wrap gap-2">
        <TableActionButton
          icon={RefreshCw}
          label={t("agents.hooksTab.neverFired.checkAgain")}
          disabled={checking}
          onClick={onCheckAgain}
        />
        <TableActionButton
          icon={Activity}
          label={t("agents.hooksTab.neverFired.openActivity")}
          onClick={() => navigate("/activity")}
        />
      </span>
    </div>
  );
}
