// src/components/agents/AgentHookCommandCell.tsx — the Command cell of one Hooks-tab row.
//
// The command itself, whole (it wraps, never truncates). Coffer's row adds what
// its state needs said: a missing hook's consequence in place of a command,
// the approval panel while Codex has not approved it, Codex's trust rule when
// it changed since approval, and the never-fired panel.
import { useTranslation } from "react-i18next";

import { AgentHookNeverFiredPanel } from "@/components/agents/AgentHookNeverFiredPanel";
import { AgentHookUntrustedPanel } from "@/components/agents/AgentHookUntrustedPanel";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import { cofferHookState, type HookRow } from "@/lib/agents/hookRows";

interface Props {
  row: HookRow;
  agentType: string;
  onCheckAgain: () => void;
  checking: boolean;
}

export function AgentHookCommandCell({ row, agentType, onCheckAgain, checking }: Props) {
  const { t } = useTranslation();
  const state = row.coffer ? cofferHookState(row.coffer) : null;

  if (row.command === null) {
    return (
      <span className="flex flex-col gap-0.5">
        <span className="text-sm font-medium text-text">{t("agents.hooksTab.missing.title")}</span>
        <span className="text-xs text-text-muted">
          {t("agents.hooksTab.missing.body", {
            file: abbreviateHomePath(row.path),
            agent: agentTypeLabel(agentType),
          })}
        </span>
      </span>
    );
  }
  return (
    <span className="flex flex-col gap-1">
      <span className="break-all font-mono text-xs text-text">{row.command}</span>
      {state?.word === "untrusted" ? (
        <AgentHookUntrustedPanel
          agentType={agentType}
          onCheckAgain={onCheckAgain}
          checking={checking}
        />
      ) : null}
      {state?.word === "modified" ? (
        <span className="text-xs text-text-muted">{t("agents.hooksTab.trustNote")}</span>
      ) : null}
      {state?.word === "neverFired" ? (
        <AgentHookNeverFiredPanel
          agentType={agentType}
          path={row.path}
          onCheckAgain={onCheckAgain}
          checking={checking}
        />
      ) : null}
    </span>
  );
}
