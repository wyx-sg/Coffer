// frontend/src/components/reach/ReachControl.tsx
// A resource's reach: one button naming it, a popover choosing it (Foundations-Reach).
//
// ONE button whose label IS the current reach — "Off", "All agents", or the
// badges of the chosen agents — opening a popover where the three modes are the
// choices (ADR per-agent-resource-scope). Pure UI: it owns the vocabulary and
// the panel, owns no resource data, fires no request.
//
//   ○ Off            No agent can use it; your ticks are kept
//   ● All agents     Including agents you add later
//   ○ Chosen agents  Only the ones ticked below      [Filter agents] [✓] [ ]
//
// Two surfaces render this exact choice and must never drift apart:
// ScopeControl (one resource, in a row or a detail header) and the add dialogs'
// drafts. BulkReachActions is the same vocabulary over a selection.
//
// EVERY CHANGE IS A WRITE. Each mode switch and each tick calls its callback at
// once — there is no Done button — and the footer says how the write is going
// (`saveState`). The panel keeps its own choice and ticks while it is open, so
// the refetch that follows a write cannot move a row out from under it; it
// re-reads the live values the next time it opens.
//
// OFF IS A CHOICE, NEVER AN INFERENCE. It is an intent with its own endpoint and
// audit events, and it deliberately leaves the scope untouched so switching
// back restores what the user had ticked. Off is also the only way to reach no
// agent: Chosen agents never holds an empty list, so switching to it with
// nothing ticked saves nothing until the first tick, and the last ticked agent
// cannot be unticked (the panel says to turn the resource off instead).
// The list sits dimmed under Off and All agents, ticks kept — the plainest
// statement that the selection survived.
//
// `initialScope` seeds the tick list: a single-resource consumer passes the
// stored scope, a fresh draft passes null.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ReachButton } from "@/components/reach/ReachButton";
import { ReachPanel } from "@/components/reach/ReachPanel";
import {
  chosenAgents,
  liveMode,
  pickableAgents,
  reachLabel,
  type ReachFailure,
  type ReachMode,
} from "@/lib/reach/reachState";
import type { SaveState } from "@/lib/reach/useReachWrites";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAgents } from "@/lib/hooks/useAgents";
import type { Scope } from "@/lib/hooks/useScope";

interface Props {
  /** The live state the button reports. */
  mode: ReachMode;
  /** Renders the button inert while a draft or write is not ready. */
  busy?: boolean;
  /** Seeds the tick list and is the scope the button shows; `null` is "everywhere". */
  initialScope?: Scope | null;
  /** Why this resource is inactive *here*, when it is. */
  note?: string;
  /** The resource's name, shown in mono at the right of the panel's head. */
  resourceName?: string;
  onDisabled: () => void;
  onEverywhere: () => void;
  /** Fired on every switch to Chosen agents and every tick, with the whole
   *  scope; `changed` is the uid just ticked (the row a failure belongs to). */
  onRestricted: (scope: Scope, changed?: string | null) => void;
  /** How the last write is going; omitted for a draft nothing writes. */
  saveState?: SaveState;
  /** The write that failed, shown on the agent's row. */
  failure?: ReachFailure | null;
  /** Fired when the popover closes. */
  onClose?: () => void;
  testId?: string;
  /** Names the button for assistive tech. */
  ariaLabel?: string;
}

/** The two modes a ReachControl panel offers besides Off, in panel order. */
const MODE_ORDER: ReachMode[] = ["disabled", "everywhere", "restricted"];

export function ReachControl({
  mode,
  busy = false,
  initialScope = null,
  note,
  resourceName,
  onDisabled,
  onEverywhere,
  onRestricted,
  saveState,
  failure = null,
  onClose,
  testId = "scope-control",
  ariaLabel,
}: Props) {
  const { t } = useTranslation();
  const { data: agentsData } = useAgents();
  // The panel's own choice and ticks: `null` until the user touches one, then
  // theirs for as long as the panel is open.
  const [choice, setChoice] = useState<ReachMode | null>(null);
  const [draft, setDraft] = useState<Scope | null>(null);

  const registered = pickableAgents(agentsData);
  const live = liveMode(mode, initialScope);
  const picked = choice ?? live;
  const selected = (draft ?? initialScope)?.agents ?? [];
  // Unknown uids get a row too, so they count towards the total.
  const total = new Set([...registered.map((a) => a.uid), ...selected]).size;

  const pick = (next: ReachMode) => {
    if (next === picked) return;
    setChoice(next);
    if (next === "disabled") return onDisabled();
    if (next === "everywhere") return onEverywhere();
    // Always a list, never `{agents: null}`: that state is "All agents".
    setDraft({ agents: selected });
    // Nothing ticked yet: show the list and wait for the first tick. An empty
    // list is never written.
    if (selected.length > 0) onRestricted({ agents: selected }, null);
  };

  const toggle = (uid: string, checked: boolean) => {
    const agents = checked ? [...selected, uid] : selected.filter((entry) => entry !== uid);
    setChoice("restricted");
    setDraft({ agents });
    // Only reachable empty through a failed row's "Untick": nothing to save.
    if (agents.length > 0) onRestricted({ agents }, checked ? uid : null);
  };

  const onOpenChange = (open: boolean) => {
    setChoice(null);
    setDraft(null);
    if (!open) onClose?.();
  };

  const names: Record<ReachMode, [string, string]> = {
    disabled: [t("scope.off"), t("scope.disabledSub")],
    everywhere: [t("scope.everywhere"), t("scope.everywhereSub")],
    restricted: [t("scope.restricted"), t("scope.restrictedSub")],
  };
  const summary =
    picked === "restricted"
      ? t("scope.countOf", { selected: selected.length, total })
      : names[picked ?? "everywhere"][0];

  return (
    <div className="inline-flex" data-testid={testId}>
      <Popover onOpenChange={onOpenChange}>
        <PopoverTrigger asChild>
          <ReachButton
            live={live}
            label={reachLabel(t, live)}
            chosen={chosenAgents(initialScope, registered)}
            disabled={busy}
            aria-label={ariaLabel}
            // The note is about THIS resource: it colours the button (a bare
            // badge would otherwise look healthy while reaching nobody on this
            // machine) and is the one thing worth a tooltip on it.
            title={note}
            warn={Boolean(note)}
          />
        </PopoverTrigger>
        <PopoverContent
          align="start"
          className="flex max-h-[480px] w-[316px] flex-col gap-2.5 p-3 text-text"
        >
          <ReachPanel
            resourceName={resourceName}
            note={note}
            modes={MODE_ORDER.map((value) => ({
              value,
              text: names[value][0],
              sub: names[value][1],
            }))}
            picked={picked}
            listMode="restricted"
            onPick={pick}
            registered={registered}
            selected={selected}
            onToggle={toggle}
            lockLast
            summary={summary}
            saveState={saveState}
            failure={failure}
          />
        </PopoverContent>
      </Popover>
    </div>
  );
}
