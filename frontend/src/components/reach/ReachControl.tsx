// frontend/src/components/reach/ReachControl.tsx
//
// The three-way reach choice — Disabled / Every agent / Selected agents —
// written ONCE, as pure UI. It owns the segment vocabulary (which segments
// exist, what they are called, which one reads as active) and the agent-picking
// popover with its staged draft; it owns NO data and fires no request.
//
// Three surfaces render this exact choice and must never drift apart:
//   • ScopeControl        — one resource, in a table row or on a detail page.
//   • BulkReachActions    — the same choice applied to a whole selection.
//   • the two-segment fallback for kinds that declare no scope, which is the
//     same control minus its third segment (`supportsScope={false}`).
// Each of them supplies the three callbacks; none of them re-implements the
// buttons, the labels, or the popover.
//
// Staging, not per-tick writes: the two whole-value segments each already name
// a complete state, so a consumer writes them immediately. A list of agents is
// only finished when the user stops picking, so the draft lives here and
// `onSelectedAgents` fires exactly once, when the panel closes. (Writing per
// tick refetched the list under the open panel, and the row it is anchored to
// moved out from under it.)
//
// `initialAgents` seeds that draft when the panel opens. A single-resource
// consumer passes the resource's current scope, so the panel opens on what is
// stored; the bulk consumer passes nothing, because a bulk write is a new
// intent rather than an edit of any one row's value.
import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAgents } from "@/lib/hooks/useAgents";

/** Which of the three segments reads as the live state. */
export type ReachMode = "disabled" | "every" | "selected";

/** The segmented-group shell, exported so a consumer that needs the same frame
 *  around something else (a pending placeholder, say) matches it exactly. */
export const REACH_GROUP_CLASS = "flex items-center gap-1 rounded-md border border-border p-0.5";

interface Props {
  /** The active segment; `null` marks none of them active — the bulk bar, where
   *  the selection has no single current reach to reflect. */
  mode: ReachMode | null;
  /** `false` collapses the group to Disabled/Enabled for a kind that declares
   *  no per-agent scope. */
  supportsScope?: boolean;
  /** Renders every segment inert while a write is in flight. */
  busy?: boolean;
  /** Seed for the agent draft when the panel opens. */
  initialAgents?: string[];
  onDisabled: () => void;
  onEveryAgent: () => void;
  /** Fired once, on panel close, with the whole staged list. */
  onSelectedAgents: (agents: string[]) => void;
  testId?: string;
  /** Names the group for assistive tech; the bulk bar sets it so the
   *  selection-wide control is distinguishable from the per-row ones. */
  ariaLabel?: string;
}

export function ReachControl({
  mode,
  supportsScope = true,
  busy = false,
  initialAgents = [],
  onDisabled,
  onEveryAgent,
  onSelectedAgents,
  testId = "scope-control",
  ariaLabel,
}: Props) {
  const { t } = useTranslation();
  const { data: agentsData } = useAgents();
  // The agent panel's staged selection: `null` while the panel is closed.
  const [draft, setDraft] = useState<string[] | null>(null);

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
        <Button {...segment(mode !== null && mode !== "disabled")} onClick={onEveryAgent}>
          {t("common.enabled")}
        </Button>
      </div>
    );
  }

  const selected = draft ?? initialAgents;
  const registered = (agentsData ?? []).map((a) => a.name);
  // A name in the list that isn't registered here is legal (a resource can be
  // scoped in before the agent exists), so it renders as an extra row.
  const unknown = selected.filter((n) => !registered.includes(n));
  const rows = [
    ...registered.map((n) => ({ name: n, known: true })),
    ...unknown.map((n) => ({ name: n, known: false })),
  ];

  const openList = (open: boolean) => {
    if (open) {
      setDraft(initialAgents);
      return;
    }
    const staged = draft;
    setDraft(null);
    if (staged === null) return;
    onSelectedAgents(staged);
  };

  const toggleAgent = (agentName: string, checked: boolean) => {
    setDraft((current) => {
      const base = current ?? selected;
      return checked ? [...base, agentName] : base.filter((a) => a !== agentName);
    });
  };

  const selectedLabel =
    selected.length > 0
      ? `${t("scope.selectedAgents")} (${selected.length})`
      : t("scope.selectedAgents");

  return (
    <div className={REACH_GROUP_CLASS} data-testid={testId} aria-label={ariaLabel}>
      <Button {...segment(mode === "disabled")} onClick={onDisabled}>
        {t("common.disabled")}
      </Button>
      <Button {...segment(mode === "every")} onClick={onEveryAgent}>
        {t("scope.everyAgent")}
      </Button>
      <Popover open={draft !== null} onOpenChange={openList}>
        <PopoverTrigger asChild>
          <Button {...segment(mode === "selected")}>
            {selectedLabel}
            <ChevronDown className="size-3.5" aria-hidden />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-80 space-y-3 p-3">
          <p className="text-xs text-muted-foreground">{t("scope.subtitle")}</p>

          {selected.length === 0 ? (
            <p className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-400">
              {t("scope.dormant")}
            </p>
          ) : null}

          {rows.length === 0 ? (
            <p className="text-xs text-muted-foreground">{t("scope.noAgents")}</p>
          ) : (
            <div className="space-y-2">
              {rows.map((row) => (
                <label
                  key={row.name}
                  data-testid={`scope-agent-${row.name}`}
                  className="flex w-full cursor-pointer items-center gap-2 rounded-md border border-border/60 p-2.5 text-sm"
                >
                  <Checkbox
                    checked={selected.includes(row.name)}
                    disabled={busy}
                    aria-label={row.name}
                    onChange={(e) => toggleAgent(row.name, e.target.checked)}
                  />
                  <span className="font-medium">{row.name}</span>
                  {!row.known ? <Badge variant="outline">{t("scope.unknownAgent")}</Badge> : null}
                </label>
              ))}
            </div>
          )}
        </PopoverContent>
      </Popover>
    </div>
  );
}
