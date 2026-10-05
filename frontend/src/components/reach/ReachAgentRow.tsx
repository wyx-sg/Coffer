// src/components/reach/ReachAgentRow.tsx — one checklist row of a reach panel, and its failed state.
//
// Foundations-Reach "Checklist row": checkbox 15 · md badge · name 13/400 · a
// state word on the right. When the write for this agent failed (4.3.09) the
// word reads "Failed" and the reason sits under the row with Retry / Untick.
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import type { PickableAgent, ReachFailure } from "@/lib/reach/reachState";

interface Props {
  agent: PickableAgent & { known: boolean };
  checked: boolean;
  disabled: boolean;
  failure: ReachFailure | null;
  onToggle: (uid: string, checked: boolean) => void;
  onRetry?: () => void;
}

export function ReachAgentRow({ agent, checked, disabled, failure, onToggle, onRetry }: Props) {
  const { t } = useTranslation();
  const word = failure
    ? null
    : !agent.known
      ? t("scope.unknownAgent")
      : agent.installed
        ? null
        : t("agentBadge.state.not-installed");
  return (
    <div data-testid={`scope-agent-${agent.name}`}>
      <label className="flex min-h-8 w-full cursor-pointer items-center gap-2 rounded-item px-2 transition-colors duration-fast hover:bg-surface-hover">
        <Checkbox
          checked={checked}
          disabled={disabled}
          aria-label={agent.label}
          onChange={(e) => onToggle(agent.uid, e.target.checked)}
        />
        {/* The name beside it is the visible text, so the badge is decoration. */}
        <span aria-hidden className="inline-flex">
          <AgentBadge
            type={agent.type}
            name={agent.label}
            size="md"
            tooltip={false}
            state={agent.installed ? undefined : "not-installed"}
          />
        </span>
        <span className="min-w-0 flex-1 truncate text-sm font-normal text-text">{agent.label}</span>
        {failure ? (
          <span className="shrink-0 text-xs font-label text-danger">{t("scope.failed")}</span>
        ) : null}
        {word ? <span className="shrink-0 text-xs text-text-muted">{word}</span> : null}
      </label>
      {failure ? (
        <div
          role="alert"
          className="mx-2 mb-1 flex flex-col gap-1 rounded-lg bg-danger-soft px-3 py-2 text-xs text-danger"
        >
          <span>{failure.message}</span>
          <span className="flex gap-1">
            <Button type="button" variant="outline" size="sm" onClick={onRetry}>
              {t("common.retry")}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => onToggle(agent.uid, false)}
            >
              {t("scope.untick", { name: agent.label })}
            </Button>
          </span>
        </div>
      ) : null}
    </div>
  );
}
