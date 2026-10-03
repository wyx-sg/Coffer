// frontend/src/components/reach/BulkReachActions.tsx
//
// The same reach choice (ReachControl) applied to a whole table selection,
// replacing the Enable / Disable pair the bulk bars used to carry.
// Enable/Disable could not say "expose these to exactly these agents", which is
// the state the per-row control has offered since ADR per-agent-resource-scope
// — so the bar offered strictly less than the row it summarises.
//
// A bulk write is a NEW INTENT, not an edit of one row's value: the control is
// mounted with `mode={null}` in its `apply` variant — the panel stages a mode
// (Off / All agents / Chosen agents) and ticks, and nothing is written until
// Apply. `mode={null}` is what makes the button honest here. In a row the
// button's label IS the current reach; a mixed selection has no current reach to
// name, so the button reads as the action it is — "Set reach…". It carries no
// "inactive here" note either: a mixed selection has no single answer to that.
//
// The ticks are tri-state when the rows say what they hold (`scope` on each
// row): ticked for an agent every row reaches, a dash for one only some rows
// reach, empty otherwise. Apply writes the SAME state to every row, so an agent
// left unticked (or dashed) is removed from all of them.
//
// Every choice writes the SAME state to EVERY selected row, fanned out with
// useBulkMutate: Promise.allSettled, so one failed row never aborts the rest,
// then one invalidation burst. Partial failure is reported in the panel (it
// stays open: "N succeeded, M failed" with a Retry), never as a toast and never
// silently; full success toasts once and clears the selection.
//
// "All agents" and "Chosen agents" are two writes per row (enable, then PUT the
// scope), sequenced inside one fan-out unit so a row that fails to enable is
// counted as failed rather than half-applied.
import type { QueryKey } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { ReachControl } from "@/components/reach/ReachControl";
import type { ReachMode } from "@/lib/reach/reachState";
import type { Scope } from "@/lib/api/scope";
import { useAgents } from "@/lib/hooks/useAgents";
import { useBulkReach } from "@/lib/hooks/useScope";

/** The minimum a row must carry to be reachable: its resource identity. `kind`
 *  is not part of any request — every route here takes the uid — it only says
 *  which kind's behaviour (and list key) the write belongs to. */
interface ReachTarget {
  kind: string;
  uid: string;
  /** The row's stored scope (`null` = every agent). Omit it where the list
   *  does not carry it: the ticks then start empty, with no dashes. */
  scope?: Scope | null;
}

interface Props {
  rows: ReachTarget[];
  /** The kind's own list key, invalidated alongside ["resources"] and
   *  ["scope"] once the batch settles (e.g. ["skills"], ["providers"]). */
  invalidate?: QueryKey[];
  /** Clears the table selection once the batch has settled. */
  onDone: () => void;
}

export function BulkReachActions({ rows, invalidate = [], onDone }: Props) {
  const { t } = useTranslation();
  const bulk = useBulkReach(invalidate);
  const { data: agents } = useAgents();
  const { ticked, partial } = tickStates(
    rows,
    (agents ?? []).map((a) => a.uid),
  );

  // A batch with a failed row REJECTS, so the panel stays open and says so
  // (the failure toast is switched off in `useBulkReach`); Retry reruns the
  // batch, which is safe — every write sets the same state.
  const settle = async (batch: Promise<{ ok: number; failed: number }>) => {
    const { ok, failed } = await batch;
    if (failed > 0) throw new Error(t("scope.bulkPartial", { ok, failed }));
    onDone();
  };
  const goDisabled = () => settle(bulk.disable(rows));
  const goEnabled = (scope: Scope | null) => settle(bulk.enable(rows, scope));

  // There is no "current one": the selection can hold rows in all three states,
  // and claiming one of them would misreport the others.
  const mode: ReachMode | null = null;

  return (
    <ReachControl
      mode={mode}
      busy={bulk.isPending}
      initialScope={ticked ? { agents: ticked } : null}
      partial={partial}
      apply
      testId="bulk-reach-control"
      ariaLabel={t("scope.bulkReach")}
      onDisabled={goDisabled}
      onEverywhere={() => goEnabled(null)}
      // Always a list: "All agents" is its own choice, and it arrives through
      // onEverywhere as the `null` the wire spells it with.
      onRestricted={(scope) => goEnabled(scope)}
    />
  );
}

/** Per agent, how many of the rows reach it: all (ticked) or some (a dash). A
 *  row on every agent reaches every registered one. `ticked` is null when any
 *  row did not say what it holds. */
function tickStates(rows: ReachTarget[], registered: string[]) {
  if (rows.length === 0 || rows.some((r) => r.scope === undefined)) {
    return { ticked: null, partial: [] as string[] };
  }
  const sets = rows.map((r) => new Set(r.scope === null ? registered : (r.scope?.agents ?? [])));
  const every = (uid: string) => sets.every((s) => s.has(uid));
  const union = new Set(sets.flatMap((s) => [...s]));
  const ticked = [...union].filter(every);
  return { ticked, partial: [...union].filter((uid) => !every(uid)) };
}
