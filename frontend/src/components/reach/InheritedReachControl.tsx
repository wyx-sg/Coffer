// frontend/src/components/reach/InheritedReachControl.tsx
// The reach of an item that lives inside a parent (a custom tool in its group): Foundations-Reach "Inherited reach".
//
// The same button and popover as ReachControl with one swap: no Off — the
// item's own switch turns it off — and in its place "Same as the group", the
// default, which follows the parent's agents. All agents and Chosen agents are
// the item's own override. Every change saves at once, like ReachControl.
//
// Pure UI over props: the caller owns the item, the writes and the save state,
// so a page can wire it to whatever endpoint holds the item's own scope.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ReachButton } from "@/components/reach/ReachButton";
import { ReachPanel } from "@/components/reach/ReachPanel";
import { chosenAgents, pickableAgents, type ReachFailure } from "@/lib/reach/reachState";
import type { SaveState } from "@/lib/reach/useReachWrites";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAgents } from "@/lib/hooks/useAgents";
import type { Scope } from "@/lib/hooks/useScope";

/** `inherited` follows the parent; the other two are the item's own override. */
export type InheritedMode = "inherited" | "everywhere" | "restricted";

interface Props {
  mode: InheritedMode;
  /** The item's own agent list; read only while `mode` is `restricted`. */
  scope?: Scope | null;
  /** The item's name, shown in mono at the right of the panel's head. */
  resourceName?: string;
  /** What "Same as the group" means right now ("deploy-api gives it to
   *  Claude Code and Codex"); replaces the row's generic sub line. */
  inheritedSub?: string;
  /** A quiet line under the list. */
  footnote?: string;
  onInherit: () => void;
  onEverywhere: () => void;
  /** Fired on every switch to Chosen agents and every tick, with the whole
   *  list; `changed` is the uid just ticked. */
  onRestricted: (scope: Scope, changed?: string | null) => void;
  saveState?: SaveState;
  failure?: ReachFailure | null;
  busy?: boolean;
  onClose?: () => void;
  testId?: string;
  ariaLabel?: string;
}

const MODE_ORDER: InheritedMode[] = ["inherited", "everywhere", "restricted"];

export function InheritedReachControl({
  mode,
  scope = null,
  resourceName,
  inheritedSub,
  footnote,
  onInherit,
  onEverywhere,
  onRestricted,
  saveState,
  failure = null,
  busy = false,
  onClose,
  testId = "inherited-reach-control",
  ariaLabel,
}: Props) {
  const { t } = useTranslation();
  const { data: agentsData } = useAgents();
  const [choice, setChoice] = useState<InheritedMode | null>(null);
  const [draft, setDraft] = useState<Scope | null>(null);

  const registered = pickableAgents(agentsData);
  const picked = choice ?? mode;
  const selected = (draft ?? scope)?.agents ?? [];
  const total = new Set([...registered.map((a) => a.uid), ...selected]).size;

  const pick = (next: InheritedMode) => {
    if (next === picked) return;
    setChoice(next);
    if (next === "inherited") return onInherit();
    if (next === "everywhere") return onEverywhere();
    setDraft({ agents: selected });
    onRestricted({ agents: selected }, null);
  };

  const toggle = (uid: string, checked: boolean) => {
    const agents = checked ? [...selected, uid] : selected.filter((entry) => entry !== uid);
    setChoice("restricted");
    setDraft({ agents });
    onRestricted({ agents }, checked ? uid : null);
  };

  const names: Record<InheritedMode, [string, string]> = {
    inherited: [t("scope.inherited"), inheritedSub ?? t("scope.inheritedSub")],
    everywhere: [t("scope.everywhere"), t("scope.everywhereSub")],
    restricted: [t("scope.restricted"), t("scope.restrictedSub")],
  };
  const summary =
    picked === "restricted"
      ? t("scope.countOf", { selected: selected.length, total })
      : names[picked][0];
  // The button: a word for the first two, the badges alone for a chosen list.
  const label =
    mode === "restricted" ? (selected.length === 0 ? t("scope.noneSelected") : "") : names[mode][0];

  return (
    <div className="inline-flex" data-testid={testId}>
      <Popover
        onOpenChange={(open) => {
          setChoice(null);
          setDraft(null);
          if (!open) onClose?.();
        }}
      >
        <PopoverTrigger asChild>
          <ReachButton
            live={mode}
            label={label}
            chosen={chosenAgents(scope, registered)}
            disabled={busy}
            aria-label={ariaLabel}
          />
        </PopoverTrigger>
        <PopoverContent
          align="start"
          className="flex max-h-[480px] w-[316px] flex-col gap-2.5 p-3 text-text"
        >
          <ReachPanel
            resourceName={resourceName}
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
            footnote={footnote}
            summary={summary}
            saveState={saveState}
            failure={failure}
          />
        </PopoverContent>
      </Popover>
    </div>
  );
}
