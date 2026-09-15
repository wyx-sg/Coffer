// frontend/src/lib/reachFilter.ts
//
// The one "Reach" filter every scoped-resource list offers. A row's reach is
// the three-state answer its ScopeControl shows — Disabled beats scope, and an
// enabled resource is either unscoped (every agent) or restricted to a chosen
// set — so the filter offers exactly those three, under the same header the
// column carries. Declared once so the MCP servers, skills, knowledge and
// memory tables cannot drift on either the states or their labels.
import type { TFunction } from "i18next";

import type { FilterDef } from "@/components/DataTable.types";
import type { Scope } from "@/lib/hooks/useScope";

export type ReachState = "disabled" | "every" | "selected";

/** The generic reach fields a row has to expose to be filterable. */
export interface ReachFields {
  enabled: boolean;
  scope: Scope | null | undefined;
}

/** A row's reach as the filter names it. */
export function reachState({ enabled, scope }: ReachFields): ReachState {
  if (!enabled) return "disabled";
  return (scope ?? null) === null ? "every" : "selected";
}

/** The filter's three choices, labelled the way ScopeControl labels them. */
export function reachFilterOptions(t: TFunction): { value: ReachState; label: string }[] {
  return [
    { value: "disabled", label: t("common.disabled") },
    { value: "every", label: t("scope.everywhere") },
    { value: "selected", label: t("scope.restricted") },
  ];
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
    accessor: (row) => reachState(pick(row)),
    options: reachFilterOptions(t),
  };
}
