// frontend/src/components/reach/reachState.ts
//
// One reach vocabulary for the whole app: the three states a scoped resource
// can be in, the single rule that decides which one a row is in, and the name
// each state goes by.
//
// It lives here, beside ReachControl, because the control's button text IS the
// answer to "which state is this in" — but the list filters ask the same
// question of a whole table (`lib/reachFilter.ts`) and the detail header's
// ScopeControl asks it of one resource, and a second copy of the rule is how
// a table's "Reach" column comes to disagree with the button in the row next
// to it. Nothing needs React, so nothing here imports it.
import type { TFunction } from "i18next";

import type { Scope } from "@/lib/hooks/useScope";

/** Which state the control reads as, and which one the panel will write. */
export type ReachMode = "disabled" | "everywhere" | "restricted";

/** The generic reach fields a row has to expose to be placed in a state. */
export interface ReachFields {
  enabled: boolean;
  scope: Scope | null | undefined;
}

/**
 * The state a resource is in. `enabled` beats scope — a switched-off resource
 * reaches nobody whatever its list says — and an enabled resource is either
 * unscoped (every agent) or restricted to a chosen set. An empty agent list is
 * still `restricted`: it names nobody, which is a different state from off,
 * with a different way back.
 */
export function reachModeOf({ enabled, scope }: ReachFields): ReachMode {
  if (!enabled) return "disabled";
  return (scope ?? null) === null ? "everywhere" : "restricted";
}

/** What a state is called, with no row in hand — a filter option, a legend. */
export function reachModeName(t: TFunction, mode: ReachMode): string {
  if (mode === "disabled") return t("common.disabled");
  return mode === "everywhere" ? t("scope.everywhere") : t("scope.restricted");
}

/**
 * The state to report, normalised. A stored scope of `{agents: null}` IS
 * "everywhere" — reading it as a restriction would check a radio that the
 * button above it contradicts, and count a list of nobody.
 */
export function liveMode(
  mode: ReachMode | null,
  supportsScope: boolean,
  scope: Scope | null,
): ReachMode | null {
  const restrictedToEveryone =
    mode === "restricted" && supportsScope && (scope?.agents ?? null) === null;
  return restrictedToEveryone ? "everywhere" : mode;
}

/**
 * The button's text: the state, said plainly.
 *
 * `null` names no state — the bulk bar, where a mixed selection has no single
 * reach — so it names the action instead. Where the control has a row in hand
 * it can be more specific than `reachModeName` and count the agents; the
 * states it cannot count it names through that function, so the button and the
 * filter option for one state can never read differently.
 *
 * An empty agent list is reported as its own thing, never as "Disabled": the
 * user did not switch that resource off, its list currently names nobody, and
 * those are different states with different ways back.
 */
export function reachLabel(
  t: TFunction,
  live: ReachMode | null,
  supportsScope: boolean,
  scope: Scope | null,
): string {
  if (live === null) return t("scope.setReach");
  if (live === "disabled") return reachModeName(t, "disabled");
  if (!supportsScope) return t("common.enabled");
  if (live === "everywhere") return reachModeName(t, "everywhere");
  const agents = scope?.agents ?? [];
  if (agents.length === 0) return t("scope.noneSelected");
  return t("scope.agentCount", { count: agents.length });
}
