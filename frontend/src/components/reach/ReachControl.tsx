// frontend/src/components/reach/ReachControl.tsx
//
// A resource's reach, as ONE button whose label IS the current reach, opening a
// panel where the states are the choices (ADR per-agent-resource-scope). Pure
// UI: it owns the vocabulary and the panel, owns no resource data, fires no
// request.
//
//   [ Every agent ▾ ]   [ 2 agents ▾ ]   [ Disabled ▾ ]
//
//   ○ Disabled     ● Every agent     ○ Only selected agents
//                                          [✓] claude-code   [ ] codex
//
// It used to be three buttons side by side — Disabled / Everywhere /
// Restricted… — in every row. Two of them said the same thing ("everywhere" is
// "restricted with every agent ticked"), so the group spent three controls on
// two states and still made the reader compare all three to learn which was
// live. One button states the answer; the panel is where it is changed.
//
// Three surfaces render this exact choice and must never drift apart:
// ScopeControl (one resource, in a row or a detail header), BulkReachActions
// (the same choice over a whole selection), and the two-choice fallback for
// kinds that declare no scope (`supportsScope={false}`) — this same button over
// Disabled / Enabled and no agent list. One button there too, not a pair, so a
// status column reads the same whatever the kind, and so that kind's users also
// meet the machine-local line a bare pair could only put in a tooltip.
//
// DISABLED IS A CHOICE, NEVER AN INFERENCE. It is an intent with its own
// endpoint, its own audit events and its own kind-level hook, and disabling
// deliberately leaves the scope untouched so re-enabling restores what the user
// had picked. So it is its own radio writing `onDisabled`, and ticking nothing
// under "only selected agents" is NOT it: that is a scope reaching nobody,
// reported as "No agent selected" — a different label, because it is a
// different thing. The panel keeps showing the remembered agent list while
// Disabled is live, which is the plainest statement that the selection
// survived.
//
// Reach is MACHINE-LOCAL: held in this vault, never converged with a remote.
// The panel says so, because nothing else the user touches would — and every
// state is now chosen in front of that line.
//
// WRITES ONCE, ON CLOSE. The panel stages a choice and hands it over exactly
// once, as it closes — the two whole-value choices close it themselves, so
// their write still lands on the way out. (Writing while the panel was open
// refetched the list underneath it, and the row it is anchored to moved out
// from under it.) An untouched panel writes NOTHING: with "Disabled" inside it,
// reporting an untouched close would POST a disable on an already-disabled
// resource — a real audit event for a glance — and the consumer has no "same
// value" to dedupe that against the way it dedupes a scope write.
//
// `initialScope` seeds the pick-list: a single-resource consumer passes the
// stored scope, the bulk consumer passes nothing, because a bulk write is a new
// intent rather than an edit of any one row's value.
import { useId, useState } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AgentPicker } from "@/components/reach/AgentPicker";
import { liveMode, reachLabel, type ReachMode } from "@/components/reach/reachState";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAgents } from "@/lib/hooks/useAgents";
import type { Scope } from "@/lib/hooks/useScope";
import { cn } from "@/lib/utils";

export type { ReachMode };

/** Narrowing from "every agent" starts on an empty list — dormant until the
 *  user picks one, which is the prompt the choice is asking for. */
const RESTRICTED_START: Scope = { agents: [] };

const WARNING_CLASS =
  "rounded border border-status-warn/40 bg-status-warn/5 px-3 py-2 text-xs text-status-warn";

interface Props {
  /** The live state the button reports; `null` marks "no single state" — the
   *  bulk bar, where a mixed selection has no current reach to name. */
  mode: ReachMode | null;
  /** `false` collapses the panel to Disabled/Enabled for a kind that declares
   *  no scope. */
  supportsScope?: boolean;
  /** Renders the button and every choice inert while a write is in flight. */
  busy?: boolean;
  /** Seeds the pick-list and is the scope the button counts; `null` is
   *  "everywhere", or a fresh intent for the bulk bar. */
  initialScope?: Scope | null;
  /** Why this resource is inactive *here*, when it is. The bulk bar passes
   *  nothing: a mixed selection has no single answer. */
  note?: string;
  onDisabled: () => void;
  onEverywhere: () => void;
  /** Fired once, on panel close, with the whole staged scope. */
  onRestricted: (scope: Scope) => void;
  testId?: string;
  /** Names the control for assistive tech; the bulk bar sets it so the
   *  selection-wide control is distinguishable from the per-row ones. */
  ariaLabel?: string;
}

export function ReachControl({
  mode,
  supportsScope = true,
  busy = false,
  initialScope = null,
  note,
  onDisabled,
  onEverywhere,
  onRestricted,
  testId = "scope-control",
  ariaLabel,
}: Props) {
  const { t } = useTranslation();
  const { data: agentsData } = useAgents();
  const [open, setOpen] = useState(false);
  // The staged choice: `null` until the user touches one, which is what tells
  // an untouched close from a deliberate one.
  const [choice, setChoice] = useState<ReachMode | null>(null);
  // The pick-list's staged selection: `null` while the panel is closed.
  const [draft, setDraft] = useState<Scope | null>(null);
  // Native radios are mutually exclusive by `name`; per-instance so two
  // controls on one page can never share a group.
  const group = useId();

  const staged = draft ?? initialScope ?? RESTRICTED_START;
  const selected = staged.agents ?? [];
  const registered = (agentsData ?? []).map((a) => a.name);
  const live = liveMode(mode, supportsScope, initialScope);
  // What reads as chosen: the staged choice, else the live state — `null` for
  // an untouched bulk panel, whose selection has no single reach.
  const picked = choice ?? live;

  // The one write: every path out of the panel runs through here, with the
  // choice passed in rather than read from state, so a pick made in this same
  // tick is not lost to a stale render.
  const finish = (committed: ReachMode | null, scope: Scope) => {
    setOpen(false);
    setChoice(null);
    setDraft(null);
    if (committed === null) return;
    if (committed === "disabled") return onDisabled();
    if (committed === "everywhere") return onEverywhere();
    // Always a list, never `{agents: null}`: that state has its own choice and
    // callback, so no consumer has to normalise one into the other.
    onRestricted({ agents: scope.agents ?? [] });
  };

  const onOpenChange = (next: boolean) => {
    if (next) {
      setChoice(null);
      setDraft(initialScope ?? RESTRICTED_START);
      setOpen(true);
      return;
    }
    finish(choice, staged);
  };

  // Ticking a row IS the pick of "only selected agents" — which is why the
  // rows stay on screen under the other choices: narrowing is one click from
  // where the user already is, not pick-the-radio-then-find.
  const toggle = (name: string, checked: boolean) => {
    const base = staged.agents ?? [];
    setChoice("restricted");
    setDraft({ agents: checked ? [...base, name] : base.filter((entry) => entry !== name) });
  };

  const choiceRow = (value: ReachMode, text: string, onPick: () => void) => (
    <label className="flex w-full cursor-pointer items-center gap-2 text-sm">
      <input
        type="radio"
        name={group}
        className="size-4 cursor-pointer accent-primary align-middle"
        checked={picked === value}
        disabled={busy}
        // `onClick`, not `onChange`: re-picking the live choice is a real
        // gesture (it is how a user confirms and closes) and an already-checked
        // radio fires no change. Keyboard activation clicks too, so nothing is
        // lost; `readOnly` only tells React the missing `onChange` is meant.
        readOnly
        onClick={onPick}
      />
      <span>{text}</span>
    </label>
  );

  return (
    <div className="inline-flex" data-testid={testId} aria-label={ariaLabel}>
      <Popover open={open} onOpenChange={onOpenChange}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy}
            // The note is about THIS resource and outranks the standing fact
            // for the tooltip. It colours the button too: one button carrying
            // the whole answer would otherwise read "2 agents" — perfectly
            // healthy-looking — while reaching nobody on this machine.
            title={note ?? t("scope.machineLocal")}
            className={cn("gap-1.5 font-normal", note && "text-status-warn")}
          >
            {reachLabel(t, live, supportsScope, initialScope)}
            <ChevronDown className="size-3.5" aria-hidden />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-96 space-y-3 p-3">
          <div className="space-y-1.5">
            <p className="text-xs text-muted-foreground">{t("scope.subtitle")}</p>
            {/* Quiet, not amber: a standing fact about where reach is kept,
                not a fault. Amber is for a scope that reaches nobody. */}
            <p className="text-xs text-muted-foreground" data-testid="reach-machine-local">
              {t("scope.machineLocal")}
            </p>
          </div>

          {note ? <p className={WARNING_CLASS}>{note}</p> : null}

          <div role="radiogroup" aria-label={t("scope.choicesLabel")} className="space-y-2">
            {choiceRow("disabled", t("common.disabled"), () => finish("disabled", staged))}
            {supportsScope ? (
              <>
                {choiceRow("everywhere", t("scope.everywhere"), () => finish("everywhere", staged))}
                {/* The one choice that leaves the panel open: it is asking a
                    question. Starting empty is also what keeps `{agents: null}`
                    out of `onRestricted`. */}
                {choiceRow("restricted", t("scope.restricted"), () => {
                  setChoice("restricted");
                  setDraft({ agents: staged.agents ?? [] });
                })}

                <AgentPicker
                  className="space-y-2 pl-6"
                  registered={registered}
                  selected={selected}
                  dormant={picked === "restricted" && selected.length === 0}
                  busy={busy}
                  onToggle={toggle}
                />
              </>
            ) : (
              // Two states only, and "enabled" is the everywhere intent under
              // the only name that means anything with no scope to narrow.
              choiceRow("everywhere", t("common.enabled"), () => finish("everywhere", staged))
            )}
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}
