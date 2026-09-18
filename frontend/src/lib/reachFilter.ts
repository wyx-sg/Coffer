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
//
// Which is also why `supportsScope` is threaded through rather than assumed. A
// kind that declares no per-agent scope (`knowledge`, `memory`) has two states,
// not three, and its control says so; an unconditional third option would be a
// "Only selected agents" choice that no row in that table can ever match —
// a filter that can only ever empty the table. The two labels still come from
// reachState, through the same function the button's text comes from, so the
// collapsed filter cannot drift from the collapsed control either.
import type { TFunction } from "i18next";

import type { FilterDef } from "@/components/DataTable.types";
import {
  reachLabel,
  reachModeName,
  reachModeOf,
  type ReachFields,
  type ReachMode,
} from "@/components/reach/reachState";

/**
 * The filter's choices, labelled the way ReachControl labels them: three for a
 * scoped kind, and Disabled/Enabled for a kind with no scope — where "enabled"
 * is what the everywhere intent is called when there is nothing to narrow.
 */
export function reachFilterOptions(
  t: TFunction,
  supportsScope = true,
): { value: ReachMode; label: string }[] {
  const modes: ReachMode[] = supportsScope
    ? ["disabled", "everywhere", "restricted"]
    : ["disabled", "everywhere"];
  return modes.map((mode) => ({
    value: mode,
    // `reachModeName` names a state with no resource in hand; with no scope to
    // narrow, the name the control uses is the one `reachLabel` gives — the
    // same call the button makes, so the two cannot read differently.
    label: supportsScope ? reachModeName(t, mode) : reachLabel(t, mode, false, null),
  }));
}

/**
 * A DataTable filter over a row's reach. `pick` maps the row to its reach
 * fields, because not every list carries them on the row itself — the
 * knowledge table merges them in from a second query.
 *
 * `supportsScope: false` collapses it to the two states such a kind has, and
 * places every enabled row in "everywhere" whatever scope its payload still
 * carries: with no scope declared, `enabled` is the whole answer.
 */
export function reachFilter<T>(
  t: TFunction,
  pick: (row: T) => ReachFields,
  supportsScope = true,
): FilterDef<T> {
  return {
    key: "reach",
    // The column it filters is headed "Status" for a kind with no scope, since
    // that is all the control reports there.
    label: t(supportsScope ? "resources.cols.reach" : "resources.cols.status"),
    allLabel: t("resources.status.all"),
    accessor: (row) => {
      const mode = reachModeOf(pick(row));
      if (supportsScope || mode === "disabled") return mode;
      return "everywhere";
    },
    options: reachFilterOptions(t, supportsScope),
  };
}
