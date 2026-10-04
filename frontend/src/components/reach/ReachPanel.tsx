// src/components/reach/ReachPanel.tsx — the body of a reach popover, shared by the reach controls.
//
// Foundations-Reach "Reach popover": a head ("Available to" + the resource name
// in mono), the radio modes, the agent list and the footer. Which modes it
// offers and what picking one does belong to the caller — ReachControl offers
// Off / All agents / Chosen agents — so this owns no state and fires no request.
import { useId } from "react";
import { useTranslation } from "react-i18next";

import { AgentPicker } from "@/components/reach/AgentPicker";
import { ReachChoice } from "@/components/reach/ReachChoice";
import { ReachPanelFooter } from "@/components/reach/ReachPanelFooter";
import { Button } from "@/components/ui/button";
import { WARNING_CLASS, type PickableAgent, type ReachFailure } from "@/lib/reach/reachState";
import type { SaveState } from "@/lib/reach/useReachWrites";

interface ReachModeRow<M extends string> {
  value: M;
  text: string;
  sub: string;
}

interface Props<M extends string> {
  resourceName?: string;
  /** Why this resource is inactive here, in amber, above the modes. */
  note?: string;
  modes: ReachModeRow<M>[];
  picked: M | null;
  /** The one mode under which the agent list is live. */
  listMode: M;
  onPick: (mode: M) => void;
  registered: PickableAgent[];
  selected: string[];
  onToggle: (uid: string, checked: boolean) => void;
  /** A quiet line under the list (the inherited control's "turn its switch off"). */
  footnote?: string;
  summary: string;
  saveState?: SaveState;
  failure?: ReachFailure | null;
  busy?: boolean;
}

export function ReachPanel<M extends string>({
  resourceName,
  note,
  modes,
  picked,
  listMode,
  onPick,
  registered,
  selected,
  onToggle,
  footnote,
  summary,
  saveState,
  failure = null,
  busy = false,
}: Props<M>) {
  const { t } = useTranslation();
  const group = useId();
  return (
    <>
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-xs font-semibold text-text">{t("scope.availableTo")}</p>
        {resourceName ? (
          <span className="min-w-0 truncate font-mono text-xs text-text-subtle">
            {resourceName}
          </span>
        ) : null}
      </div>

      {note ? <p className={WARNING_CLASS}>{note}</p> : null}

      <div
        role="radiogroup"
        aria-label={t("scope.choicesLabel")}
        className="border-b border-border-subtle pb-2.5"
      >
        {modes.map((m) => (
          <ReachChoice
            key={m.value}
            group={group}
            checked={picked === m.value}
            disabled={busy}
            text={m.text}
            sub={m.sub}
            onPick={() => onPick(m.value)}
          />
        ))}
      </div>

      {failure && failure.uid === null ? (
        <div
          role="alert"
          className="flex flex-col gap-1 rounded-lg bg-danger-soft px-3 py-2 text-xs text-danger"
        >
          <span>{failure.message}</span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="self-start"
            onClick={failure.retry}
          >
            {t("common.retry")}
          </Button>
        </div>
      ) : null}

      <AgentPicker
        className="flex-1"
        registered={registered}
        selected={selected}
        dormant={picked === listMode && selected.length === 0}
        active={picked === listMode}
        busy={busy}
        failure={failure}
        onRetry={failure?.retry}
        onToggle={onToggle}
      />

      {footnote ? <p className="text-xs text-text-muted">{footnote}</p> : null}

      <ReachPanelFooter summary={summary} saveState={saveState} failed={failure !== null} />
    </>
  );
}
