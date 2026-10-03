// frontend/src/components/reach/ReachControl.tsx
// A resource's reach: one button naming it, a panel choosing it (Foundations 0.7.02).
//
// ONE button whose label IS the current reach, opening a panel where the three
// modes are the choices. Pure UI: it owns the vocabulary and the panel, owns no
// resource data, and fires the callbacks it is given.
//
//   [ Off ▾ ]    [ All agents ▾ ]    [ (claude)(codex) ▾ ]    [ No agent ▾ ]
//
//   Available to / <resource name>
//   ○ Off              No agent can use it; your ticks are kept
//   ○ All agents       Including agents you add later
//   ● Chosen agents    Only the ones ticked below
//   [ Filter agents ]  [✓] claude   [ ] codex
//   1 of 2 agents                                      ✓ Saved
//
// OFF IS A CHOICE, NEVER AN INFERENCE. It is an intent with its own endpoint,
// its own audit events and its own kind-level hook, and it deliberately leaves
// the scope untouched so switching back restores what the user had ticked. So
// it is its own radio writing `onDisabled`, and ticking nothing under "Chosen
// agents" is NOT it: that is a list reaching nobody, reported as "No agent" —
// a different label, because it is a different thing.
//
// SWITCHING TO "CHOSEN AGENTS" writes the list the resource last held (the
// scope still stored, or the ticks remembered from before an "All agents"
// cleared them); with no such list it writes the empty list. That is honest:
// the stored state after a reload is exactly what the panel shows (reads "No
// agent", "0 of 2 agents") — a Chosen radio over a stored "All agents" would
// not survive a reload.
//
// The `apply` variant (the bulk bar) is a new intent over a whole selection,
// not an edit of one row: nothing is written while the panel is open — the
// panel stages the mode and ticks, and Apply hands them over once. `partial`
// marks agents ticked on some of the selected rows (drawn as a dash).
//
import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { ReachButton } from "@/components/reach/ReachButton";
import { ReachChoice } from "@/components/reach/ReachChoice";
import { ReachPanel } from "@/components/reach/ReachPanel";
import { useReachWrites, type View, type Write } from "@/components/reach/useReachWrites";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { translateApiError } from "@/lib/api/errors";
import { useAgents } from "@/lib/hooks/useAgents";
import type { Scope } from "@/lib/hooks/useScope";
import {
  chosenAgents,
  liveMode,
  pickableAgents,
  reachLabel,
  type ReachMode,
} from "@/lib/reach/reachState";

interface Props {
  /** The live state the button reports; `null` marks "no single state" — the
   *  bulk bar, where a mixed selection has no current reach to name. */
  mode: ReachMode | null;
  /** Renders the button and every choice inert (a bulk write in flight). */
  busy?: boolean;
  /** The stored scope the list shows and the button draws; `null` is
   *  "everywhere", or a fresh intent for the bulk bar. */
  initialScope?: Scope | null;
  /** Why this resource is inactive *here*, when it is. The bulk bar passes
   *  nothing: a mixed selection has no single answer. */
  note?: string;
  /** The resource's name, shown small under the panel title. */
  resourceName?: string;
  onDisabled: Write;
  onEverywhere: Write;
  /** The whole list after a mode switch or a tick (instant), or the staged
   *  list on Apply. Always a list, never `{agents: null}`. */
  onRestricted: (scope: Scope) => void | Promise<unknown>;
  /** The bulk variant: stage in the panel, write once on Apply. */
  apply?: boolean;
  /** Bulk only: agent uids ticked on some, not all, of the selected rows. */
  partial?: string[];
  testId?: string;
  /** Names the button for assistive tech; the bulk bar sets it so the
   *  selection-wide control is distinguishable from the per-row ones. */
  ariaLabel?: string;
}

const NO_PARTIAL: string[] = [];

export function ReachControl({
  mode,
  busy = false,
  initialScope = null,
  note,
  resourceName,
  onDisabled,
  onEverywhere,
  onRestricted,
  apply = false,
  partial = NO_PARTIAL,
  testId = "scope-control",
  ariaLabel,
}: Props) {
  const { t } = useTranslation();
  const { data: agentsData } = useAgents();
  const [open, setOpen] = useState(false);
  // Optimistic view: set by a click, dropped when the props move or a write fails.
  const [override, setOverride] = useState<View | null>(null);
  const [draft, setDraft] = useState<View>({ mode: null, scope: null });
  const viewRef = useRef<View>({ mode: null, scope: null });
  const { save, setSave, failure, setFailure, pending, run } = useReachWrites(viewRef, setOverride);
  // The last list this resource held; survives an "All agents" that clears it.
  const remembered = useRef<string[] | null>(null);
  // Per-instance radio group name: two controls never share a group.
  const group = useId();

  const live = liveMode(mode, initialScope);
  // New props from outside (the refetch after a write) replace the optimistic
  // view — unless a write is still queued behind it.
  const sig = `${mode ?? ""}|${JSON.stringify(initialScope)}`;
  const [seenSig, setSeenSig] = useState(sig);
  if (sig !== seenSig) {
    setSeenSig(sig);
    if (pending.current === 0) setOverride(null);
  }

  const view: View = apply ? draft : (override ?? { mode: live, scope: initialScope });
  viewRef.current = view;
  if (view.scope?.agents) remembered.current = view.scope.agents;

  // The button follows the optimistic view too, so it moves on the click; the
  // bulk button never names a state.
  const shown: View = apply ? { mode: live, scope: initialScope } : view;
  const picked = view.mode;
  const selected = view.scope?.agents ?? [];
  const registered = pickableAgents(agentsData);
  // Unknown uids get a row too, so they count towards the total.
  const total = new Set([...registered.map((a) => a.uid), ...selected]).size;

  const stage = (next: View) => {
    viewRef.current = next;
    setDraft(next);
  };

  const pickMode = (value: ReachMode) => {
    if (viewRef.current.mode === value) return;
    const list = viewRef.current.scope?.agents ?? remembered.current ?? [];
    const next: View = {
      mode: value,
      scope: value === "everywhere" ? null : { agents: list },
    };
    if (apply) return stage(next);
    if (value === "disabled") return run(next, onDisabled);
    if (value === "everywhere") return run(next, onEverywhere);
    run(next, () => onRestricted({ agents: list }));
  };

  const toggle = (uid: string, checked: boolean) => {
    const base = viewRef.current.scope?.agents ?? [];
    const list = checked ? [...base, uid] : base.filter((entry) => entry !== uid);
    const next: View = { mode: "restricted", scope: { agents: list } };
    if (apply) return stage(next);
    run(next, () => onRestricted({ agents: list }), uid);
  };

  const onOpenChange = (next: boolean) => {
    setOpen(next);
    if (!next) return;
    setSave("idle");
    setFailure(null);
    // A fresh bulk intent starts empty; an edit starts on the stored value.
    if (apply) setDraft({ mode: null, scope: initialScope });
  };

  // Apply hands the staged state over once. The panel closes when the write
  // succeeds; a rejection keeps it open with the reason and a Retry.
  const applyNow = async () => {
    const { mode: chosen, scope } = viewRef.current;
    const write = (): void | Promise<unknown> =>
      chosen === "disabled"
        ? onDisabled()
        : chosen === "everywhere"
          ? onEverywhere()
          : onRestricted({ agents: scope?.agents ?? [] });
    setSave("saving");
    setFailure(null);
    try {
      await write();
      setSave("idle");
      setOpen(false);
    } catch (error) {
      setSave("failed");
      setFailure({ message: translateApiError(t, error), retry: () => void applyNow() });
    }
  };

  const choiceRow = (value: ReachMode, text: string, sub: string) => (
    <ReachChoice
      group={group}
      checked={picked === value}
      disabled={busy}
      {...{ text, sub }}
      onPick={() => pickMode(value)}
    />
  );

  return (
    <div className="inline-flex" data-testid={testId}>
      <Popover open={open} onOpenChange={onOpenChange}>
        <PopoverTrigger asChild>
          <ReachButton
            live={shown.mode}
            label={reachLabel(t, shown.mode, shown.scope)}
            chosen={chosenAgents(shown.scope, registered)}
            disabled={busy}
            aria-label={ariaLabel}
            // The note is about THIS resource: it colours the button and is the
            // one thing worth a tooltip on it.
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
            choices={
              <>
                {choiceRow("disabled", t("common.disabled"), t("scope.disabledSub"))}
                {choiceRow("everywhere", t("scope.everywhere"), t("scope.everywhereSub"))}
                {choiceRow("restricted", t("scope.restricted"), t("scope.restrictedSub"))}
              </>
            }
            failure={failure}
            registered={registered}
            selected={selected}
            partial={partial}
            inactive={picked !== "restricted"}
            busy={busy}
            picked={picked}
            total={total}
            save={save}
            onToggle={toggle}
            onApply={apply ? () => void applyNow() : undefined}
            applyDisabled={picked === null || save === "saving"}
          />
        </PopoverContent>
      </Popover>
    </div>
  );
}
