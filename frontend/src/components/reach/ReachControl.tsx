// frontend/src/components/reach/ReachControl.tsx
//
// The three-way reach choice — Disabled / Everywhere / Restricted… — written
// ONCE, as pure UI. It owns the segment vocabulary (which segments exist, what
// they are called, which one reads as active) and the restriction panel with
// its staged draft; it owns no resource data and fires no request.
//
// Three surfaces render this exact choice and must never drift apart:
//   • ScopeControl        — one resource, in a table row or on a detail page.
//   • BulkReachActions    — the same choice applied to a whole selection.
//   • the two-segment fallback for kinds that declare no scope, which is the
//     same control minus its third segment (`supportsScope={false}`).
// Each of them supplies the three callbacks; none of them re-implements the
// buttons, the labels, or the panel.
//
// "Restricted" is TWO axes, not one (spec vault-sync `### Scope gains a machine
// axis`): which agents, and which machines. They are independent allow-lists,
// `AND`-ed, and both are rendered by the same `ScopeAxisPicker` — which is a
// PICK-LIST and never free text, because a machine is named by its derived id
// and a mistyped id silently makes the resource dormant rather than failing.
// The two pick-lists live HERE rather than in one consumer, so the bulk bar
// offers exactly what a row offers.
//
// Staging, not per-tick writes: the two whole-value segments each already name
// a complete state, so a consumer writes them immediately. A selection is only
// finished when the user stops picking, so the draft lives here and
// `onRestricted` fires exactly once, when the panel closes. (Writing per tick
// refetched the list under the open panel, and the row it is anchored to moved
// out from under it.)
//
// `initialScope` seeds that draft when the panel opens. A single-resource
// consumer passes the resource's current scope, so the panel opens on what is
// stored; the bulk consumer passes nothing, because a bulk write is a new
// intent rather than an edit of any one row's value.
import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScopeAxisPicker, type AxisOption } from "@/components/ScopeAxisPicker";
import { useAgents } from "@/lib/hooks/useAgents";
import { useMachines } from "@/lib/hooks/useMachines";
import type { Scope } from "@/lib/hooks/useScope";

/** Which of the three segments reads as the live state. */
export type ReachMode = "disabled" | "everywhere" | "restricted";

/** The segmented-group shell, exported so a consumer that needs the same frame
 *  around something else (a pending placeholder, say) matches it exactly. */
export const REACH_GROUP_CLASS = "flex items-center gap-1 rounded-md border border-border p-0.5";

/** Opening "Restricted" from "Everywhere" starts on the agent axis, dormant
 *  until the user picks one — the same prompt the single-axis control gave. */
const RESTRICTED_START: Scope = { agents: [], machines: null };

const WARNING_CLASS =
  "rounded border border-status-warn/40 bg-status-warn/5 px-3 py-2 text-xs text-status-warn";

interface Props {
  /** The active segment; `null` marks none of them active — the bulk bar, where
   *  the selection has no single current reach to reflect. */
  mode: ReachMode | null;
  /** `false` collapses the group to Disabled/Enabled for a kind that declares
   *  no scope. */
  supportsScope?: boolean;
  /** Renders every segment inert while a write is in flight. */
  busy?: boolean;
  /** Seed for the draft when the panel opens; `null` is a fresh intent. */
  initialScope?: Scope | null;
  /** Why this resource is inactive *here*, when it is — named by the consumer
   *  that knows the stored scope. The bulk bar passes nothing, since a mixed
   *  selection has no single answer. */
  note?: string;
  onDisabled: () => void;
  onEverywhere: () => void;
  /** Fired once, on panel close, with the whole staged scope. */
  onRestricted: (scope: Scope) => void;
  testId?: string;
  /** Names the group for assistive tech; the bulk bar sets it so the
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
  const { data: machinesData } = useMachines();
  // The pick-lists' staged selection: `undefined` while the panel is closed.
  const [draft, setDraft] = useState<Scope | undefined>(undefined);

  // Shared look for one segment of the group: the active one is filled, the
  // rest are quiet, and every one of them is inert while a write is in flight.
  const segment = (active: boolean) =>
    ({
      type: "button",
      size: "sm",
      variant: active ? "secondary" : "ghost",
      "aria-pressed": active,
      disabled: busy,
    }) as const;

  if (!supportsScope) {
    return (
      <div className={REACH_GROUP_CLASS} data-testid={testId} aria-label={ariaLabel}>
        <Button {...segment(mode === "disabled")} onClick={onDisabled}>
          {t("common.disabled")}
        </Button>
        <Button {...segment(mode !== null && mode !== "disabled")} onClick={onEverywhere}>
          {t("common.enabled")}
        </Button>
      </div>
    );
  }

  const staged = draft ?? initialScope ?? RESTRICTED_START;
  const agentOptions: AxisOption[] = (agentsData ?? []).map((a) => ({ id: a.name, label: a.name }));
  const machineOptions: AxisOption[] = (machinesData?.machines ?? []).map((m) => ({
    id: m.machine_id,
    label: m.name,
    detail: m.machine_id.slice(0, 8),
    isLocal: m.is_self,
  }));
  const dormant = staged.agents?.length === 0 || staged.machines?.length === 0;

  const openList = (open: boolean) => {
    if (open) {
      setDraft(initialScope ?? RESTRICTED_START);
      return;
    }
    const stagedOnClose = draft;
    setDraft(undefined);
    if (stagedOnClose === undefined) return;
    onRestricted(stagedOnClose);
  };

  return (
    <div className={REACH_GROUP_CLASS} data-testid={testId} aria-label={ariaLabel}>
      <Button {...segment(mode === "disabled")} onClick={onDisabled}>
        {t("common.disabled")}
      </Button>
      <Button {...segment(mode === "everywhere")} onClick={onEverywhere}>
        {t("scope.everywhere")}
      </Button>
      <Popover open={draft !== undefined} onOpenChange={openList}>
        <PopoverTrigger asChild>
          <Button {...segment(mode === "restricted")} title={note}>
            {t("scope.restricted")}
            <ChevronDown className="size-3.5" aria-hidden />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-96 space-y-3 p-3">
          <p className="text-xs text-muted-foreground">{t("scope.subtitle")}</p>

          {note ? <p className={WARNING_CLASS}>{note}</p> : null}
          {dormant ? <p className={WARNING_CLASS}>{t("scope.dormant")}</p> : null}

          <ScopeAxisPicker
            titleKey="scope.agentsSection"
            everyKey="scope.everyAgent"
            emptyKey="scope.noAgents"
            unknownKey="scope.unknownAgent"
            options={agentOptions}
            value={staged.agents}
            onChange={(agents) => setDraft({ ...staged, agents })}
            disabled={busy}
            testIdPrefix="scope-agent"
          />
          <ScopeAxisPicker
            titleKey="scope.machinesSection"
            everyKey="scope.everyMachine"
            emptyKey="scope.noMachines"
            unknownKey="scope.unknownMachine"
            options={machineOptions}
            value={staged.machines}
            onChange={(machines) => setDraft({ ...staged, machines })}
            disabled={busy}
            testIdPrefix="scope-machine"
          />
        </PopoverContent>
      </Popover>
    </div>
  );
}
