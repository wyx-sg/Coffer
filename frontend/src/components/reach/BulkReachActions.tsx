// frontend/src/components/reach/BulkReachActions.tsx
//
// The same reach choice (ReachControl) applied to a whole table selection,
// replacing the Enable / Disable pair the bulk bars used to carry.
// Enable/Disable could not say "expose these to exactly these agents", which is
// the state the per-row control has offered since ADR per-agent-resource-scope
// — so the bar offered strictly less than the row it summarises.
//
// A bulk write is a NEW INTENT, not an edit of one row's value: the control is
// mounted with `mode={null}` and the pick-list opens on an EMPTY draft rather
// than on whichever row happened to be first. `mode={null}` is what makes the
// button honest here. In a row the button's label IS the current reach; a mixed
// selection has no current reach to name, so naming any one of them would
// misreport the others. Instead the button reads as the action it is — "Set
// reach…" — no choice starts out selected, and closing the panel without
// picking one writes nothing. It carries no "inactive here" note either: a
// mixed selection has no single answer to that question.
//
// Every choice writes the SAME state to EVERY selected row, fanned out with
// useBulkMutate: Promise.allSettled, so one failed row never aborts the rest,
// then one summary toast ("N succeeded, M failed") and one invalidation burst.
// Partial failure is therefore reported, never silent.
//
// "Every agent" and "Only selected agents" are two writes per row (enable,
// then PUT the scope), sequenced inside one fan-out unit so a row that fails to
// enable is counted as failed rather than half-applied.
import type { QueryKey } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { ReachControl, type ReachMode } from "@/components/reach/ReachControl";
import { resourcesApi } from "@/lib/api/resources";
import { scopeApi, type Scope } from "@/lib/api/scope";
import { agentsKey, resourcesKey, scopeKey } from "@/lib/api/queryKeys";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";

/** The minimum a row must carry to be reachable: its resource identity. */
export interface ReachTarget {
  kind: string;
  name: string;
}

interface Props {
  rows: ReachTarget[];
  /** `false` for a kind with no scope: the panel collapses to
   *  Disabled/Enabled and the choices write only the `enabled` flag. */
  supportsScope?: boolean;
  /** The kind's own list key, invalidated alongside ["resources"] and
   *  ["scope"] once the batch settles (e.g. ["skills"], ["providers"]). */
  invalidate?: QueryKey[];
  /** Clears the table selection once the batch has settled. */
  onDone: () => void;
}

export function BulkReachActions({ rows, supportsScope = true, invalidate = [], onDone }: Props) {
  const { t } = useTranslation();
  const bulk = useBulkMutate({
    invalidate: [resourcesKey, scopeKey, agentsKey, ...invalidate],
  });

  const runAll = async (apply: (row: ReachTarget) => Promise<unknown>) => {
    await bulk.run(rows, apply);
    onDone();
  };

  const goDisabled = () => void runAll((r) => resourcesApi.disable(r.kind, r.name));

  const goEnabled = (scope: Scope | null) =>
    void runAll(async (r) => {
      await resourcesApi.enable(r.kind, r.name);
      if (supportsScope) await scopeApi.put(r.kind, r.name, scope);
    });

  // There is no "current one": the selection can hold rows in all three states,
  // and claiming one of them would misreport the others.
  const mode: ReachMode | null = null;

  return (
    <ReachControl
      mode={mode}
      supportsScope={supportsScope}
      busy={bulk.isPending}
      initialScope={null}
      testId="bulk-reach-control"
      ariaLabel={t("scope.bulkReach")}
      onDisabled={goDisabled}
      onEverywhere={() => goEnabled(null)}
      // Always a list: "every agent" is its own choice, and it arrives through
      // onEverywhere as the `null` the wire spells it with.
      onRestricted={(scope) => goEnabled(scope)}
    />
  );
}
