// frontend/src/lib/reachFilter.ts
//
// The one "Reach" filter every scoped-resource list offers — the choices and
// the matching rule, and nothing else (the control that draws them is
// `components/reach/ReachFilter.tsx`).
//
// The states, the rule that places a row in one, and the name each one goes by
// all come from `lib/reach/reachState.ts`, the same module ReachControl
// draws its button text from. That is the point: the filter offers exactly the
// states the control shows, under the same labels, so the MCP servers, skills
// and custom-tool lists cannot drift from each other or from the control in
// the row beside them.
import type { TFunction } from "i18next";

import {
  reachModeName,
  reachModeOf,
  type ReachFields,
  type ReachMode,
} from "@/lib/reach/reachState";

const MODES: ReachMode[] = ["disabled", "everywhere", "restricted"];

/** What a reach filter is set to: one state, or `all` (no filtering). */
export type ReachFilterValue = "all" | ReachMode;

/** The filter's choices, labelled the way ReachControl labels them. */
export function reachFilterOptions(t: TFunction): { value: ReachMode; label: string }[] {
  return MODES.map((mode) => ({ value: mode, label: reachModeName(t, mode) }));
}

/** Whether a row passes the filter — the same rule that places it in a state. */
export function matchesReach(filter: ReachFilterValue, row: ReachFields): boolean {
  return filter === "all" || reachModeOf(row) === filter;
}
