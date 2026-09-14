// frontend/src/components/reach/reachState.ts
//
// The two pure questions behind ReachControl's one button: WHICH state a
// resource is actually in, and what that state is CALLED. Split out of the
// component because neither needs React, and because the label is the whole
// point of the redesign — the button's text is the answer, so the rule that
// produces it deserves to be readable on its own.
import type { TFunction } from "i18next";

import type { Scope } from "@/lib/hooks/useScope";

/** Which state the control reads as, and which one the panel will write. */
export type ReachMode = "disabled" | "everywhere" | "restricted";

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
 * reach — so it names the action instead. And an empty agent list is reported
 * as its own thing, never as "Disabled": the user did not switch that resource
 * off, its list currently names nobody, and those are different states with
 * different ways back.
 */
export function reachLabel(
  t: TFunction,
  live: ReachMode | null,
  supportsScope: boolean,
  scope: Scope | null,
): string {
  if (live === null) return t("scope.setReach");
  if (live === "disabled") return t("common.disabled");
  if (!supportsScope) return t("common.enabled");
  if (live === "everywhere") return t("scope.everywhere");
  const agents = scope?.agents ?? [];
  if (agents.length === 0) return t("scope.noneSelected");
  return t("scope.agentCount", { count: agents.length });
}
