// frontend/src/lib/reachFilter.ts
//
// The one "Reach" filter every scoped-resource list offers — the DataTable
// adapter over the shared reach vocabulary, and nothing else.
//
// The states, the rule that places a row in one, and the name each one goes by
// all come from `components/reach/reachState.ts`, the same module ReachControl
// draws its button text from. That is the point: the filter offers exactly the
// states the control shows, under the same labels, so the MCP servers, skills,
// knowledge, memory and connections tables cannot drift from each other or
// from the control in the row beside them.
import type { TFunction } from "i18next";

import type { FilterDef } from "@/components/DataTable.types";
import {
  reachModeName,
  reachModeOf,
  type ReachFields,
  type ReachMode,
} from "@/components/reach/reachState";

/** The filter's three choices, labelled the way ReachControl labels them. */
export function reachFilterOptions(t: TFunction): { value: ReachMode; label: string }[] {
  return (["disabled", "everywhere", "restricted"] as const).map((mode) => ({
    value: mode,
    label: reachModeName(t, mode),
  }));
}

/**
 * A DataTable filter over a row's reach. `pick` maps the row to its reach
 * fields, because not every list carries them on the row itself — the
 * knowledge table merges them in from a second query.
 */
export function reachFilter<T>(t: TFunction, pick: (row: T) => ReachFields): FilterDef<T> {
  return {
    key: "reach",
    label: t("resources.cols.reach"),
    allLabel: t("resources.status.all"),
    accessor: (row) => reachModeOf(pick(row)),
    options: reachFilterOptions(t),
  };
}
