// frontend/src/lib/skills/delivery.ts
// Where each registered agent's copy of one skill stands — the Delivery tab's
// rows, derived in the client (design add-skill-sources decision 8): from the
// skill's own bindings, the agents list with each agent's switch, and, once
// the user has asked for it, the drift report of "Report skill drift on
// request". There is no read route for this; everything it needs is already
// on the wire.
//
// Precedence per agent: a drift finding (only after Check again) beats the
// binding, because it is the fresher, on-disk answer; a binding says the copy
// is linked or copied; without one the copy is not delivered, and the reason
// is the first that applies — the skill is off, the agent is outside its
// reach, the agent itself is switched off.
import type { AgentOut } from "@/lib/api/agents";
import type { SkillDriftEntry, SkillOut } from "@/lib/api/skills";

type DriftKind = SkillDriftEntry["kind"];

type NotDeliveredReason = "skillOff" | "outsideReach" | "agentOff" | "pending";

/** One agent's copy of the skill, as the Delivery tab shows it. */
export type AgentDelivery =
  | { state: "linked"; path: string | null }
  | { state: "copied"; path: string | null }
  | { state: "drift"; kind: DriftKind; path: string }
  | { state: "notDelivered"; reason: NotDeliveredReason };

export interface DeliveryRow {
  agent: AgentOut;
  delivery: AgentDelivery;
}

/**
 * One row per registered agent, in the order given (the caller sorts them in
 * Agents-page order). `agentEnabled` answers whether an agent is switched on —
 * its generic resource flag, which `AgentOut` does not carry; an agent it
 * does not know is taken to be on. `drift` is the last report, or `null`
 * before the user has checked.
 */
export function deliveryRows(
  skill: SkillOut,
  agents: readonly AgentOut[],
  agentEnabled: (uid: string) => boolean,
  drift: readonly SkillDriftEntry[] | null,
): DeliveryRow[] {
  return agents.map((agent) => ({
    agent,
    delivery: deliveryFor(skill, agent, agentEnabled, drift),
  }));
}

function deliveryFor(
  skill: SkillOut,
  agent: AgentOut,
  agentEnabled: (uid: string) => boolean,
  drift: readonly SkillDriftEntry[] | null,
): AgentDelivery {
  const finding = drift?.find((e) => e.skill_name === skill.name && e.agent_name === agent.name);
  if (finding) {
    return { state: "drift", kind: finding.kind, path: finding.target_path };
  }
  const binding = skill.bindings.find((b) => b.agent_uid === agent.uid);
  if (binding) {
    return binding.link_mode === "copy_fallback"
      ? { state: "copied", path: binding.last_link_path }
      : { state: "linked", path: binding.last_link_path };
  }
  if (!skill.enabled) return { state: "notDelivered", reason: "skillOff" };
  const scoped = skill.scope?.agents ?? null;
  if (scoped !== null && !scoped.includes(agent.uid)) {
    return { state: "notDelivered", reason: "outsideReach" };
  }
  if (!agentEnabled(agent.uid)) return { state: "notDelivered", reason: "agentOff" };
  return { state: "notDelivered", reason: "pending" };
}

/** Whether the skill's reach grants this agent a copy — what the row's switch
 *  shows. A grant not yet on disk ("pending") still counts as on. */
export function isGranted(d: AgentDelivery): boolean {
  return d.state !== "notDelivered" || d.reason === "pending";
}

/** What flipping one agent's switch writes: whether to enable the skill first
 *  and the scope to put (`undefined` = leave it). */
export interface DeliveryWrite {
  enable: boolean;
  scope?: { agents: string[] };
}

/**
 * The write behind one switch. On a disabled skill, turning an agent on enables
 * the skill for that agent alone. Otherwise the scope is edited as a list:
 * turning on adds the agent (nothing to write when the scope is already
 * "every agent"), turning off removes it from the current list or, for "every
 * agent", from the list of all `agentUids`.
 */
export function deliveryWrite(
  skill: SkillOut,
  agentUid: string,
  on: boolean,
  agentUids: readonly string[],
): DeliveryWrite | null {
  if (!skill.enabled) return on ? { enable: true, scope: { agents: [agentUid] } } : null;
  const current = skill.scope?.agents ?? null;
  if (on) {
    if (current === null) return null;
    return current.includes(agentUid)
      ? null
      : { enable: false, scope: { agents: [...current, agentUid] } };
  }
  const base = current ?? [...agentUids];
  return { enable: false, scope: { agents: base.filter((uid) => uid !== agentUid) } };
}
