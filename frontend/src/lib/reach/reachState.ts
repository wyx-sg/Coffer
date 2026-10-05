// frontend/src/lib/reach/reachState.ts
//
// One reach vocabulary for the whole app: the three states a scoped resource
// can be in, the single rule that decides which one a row is in, and the name
// each state goes by.
//
// It lives here, beside ReachControl, because the control's button text IS the
// answer to "which state is this in" — but the bulk reach bar asks the same
// question of a whole selection and the detail header's ScopeControl asks it
// of one resource, and a second copy of the rule is how
// a table's "Reach" column comes to disagree with the button in the row next
// to it. Nothing needs React, so nothing here imports it.
import type { TFunction } from "i18next";

import { agentDisplayName } from "@/lib/agents/display";
import type { AgentOut } from "@/lib/api/agents";
import type { Scope } from "@/lib/hooks/useScope";

/** The panel's amber line: a scope, or this resource, that reaches nobody. */
export const WARNING_CLASS = "rounded-lg bg-warning-soft px-3 py-2 text-xs text-warning";

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
  if (mode === "disabled") return t("scope.off");
  return mode === "everywhere" ? t("scope.everywhere") : t("scope.restricted");
}

/**
 * The state to report, normalised. A stored scope of `{agents: null}` IS
 * "everywhere" — reading it as a restriction would check a radio that the
 * button above it contradicts, and count a list of nobody.
 */
export function liveMode(mode: ReachMode | null, scope: Scope | null): ReachMode | null {
  const restrictedToEveryone = mode === "restricted" && (scope?.agents ?? null) === null;
  return restrictedToEveryone ? "everywhere" : mode;
}

/**
 * The button's text: the state, said plainly — and nothing for a chosen list.
 *
 * Off and All agents are words; Chosen agents is the agent badges alone, so a
 * count never appears on a button or a row ("1 of 2 agents" lives in the
 * popover footer only). `null` names no state — the bulk bar — so it names the
 * action instead: "Reach".
 *
 * An empty chosen list is reported as its own thing, never as "Off": the user
 * did not switch that resource off, its list currently names nobody, and those
 * are different states with different ways back.
 */
export function reachLabel(t: TFunction, live: ReachMode | null, scope: Scope | null): string {
  if (live === null) return t("scope.setReach");
  if (live !== "restricted") return reachModeName(t, live);
  return (scope?.agents ?? []).length === 0 ? t("scope.noneSelected") : "";
}

/** One agent the pick-list can offer: what a tick WRITES (the uid), what it
 *  READS as (the name), and the type its badge is drawn from. */
export interface PickableAgent {
  uid: string;
  name: string;
  /** What a person reads: the display name (`Claude Code`), not the key in `name`. */
  label: string;
  /** Agent type key; unknown or empty draws the neutral mark. */
  type: string;
  /** False when detection finds no program on this machine — the only state
   *  the agent list carries, so the only state word a row can show. */
  installed: boolean;
}

/** The pick-list's vocabulary, from the agents registered on this machine. */
export function pickableAgents(agents: readonly AgentOut[] | undefined): PickableAgent[] {
  return (agents ?? []).map((a) => ({
    uid: a.uid,
    name: a.name,
    label: agentDisplayName(a),
    type: a.type ?? "",
    installed: a.state !== "config_only" && a.state !== "missing",
  }));
}

/** The agents a stored scope names, resolved for their badges. A uid this
 *  vault does not know keeps the neutral mark, as the pick-list keeps its row. */
export function chosenAgents(scope: Scope | null, registered: PickableAgent[]): PickableAgent[] {
  return (scope?.agents ?? []).map(
    (uid) =>
      registered.find((a) => a.uid === uid) ?? {
        uid,
        name: uid,
        label: uid,
        type: "",
        installed: true,
      },
  );
}

/** A write the popover could not land. `uid` names the agent row it belongs to
 *  (the one just ticked); `null` is a failure with no single agent behind it. */
export interface ReachFailure {
  uid: string | null;
  message: string;
  retry: () => void;
}
