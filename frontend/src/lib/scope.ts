// frontend/src/lib/scope.ts
//
// Pure helpers over a resource's two-axis activation scope (ADR
// per-agent-resource-scope, spec vault-sync `### Scope gains a machine axis`).
// They mirror `backend/coffer/domain/scope.py`, which is the authority; keep
// the two in step.
//
// A separate module from `hooks/useScope.ts` on purpose: these are functions,
// not hooks, and a test that mocks the hook module must not lose them with it.
import type { Scope } from "@/lib/hooks/useScope";

/** Which axis kept a resource dormant, for a UI that has to explain itself. */
export type ExclusionAxis = "machine" | "agent";

/** True when the two scopes name the same thing on both axes. */
export function sameScope(a: Scope | null, b: Scope | null): boolean {
  if (a === null || b === null) return a === b;
  return sameAxis(a.agents, b.agents) && sameAxis(a.machines, b.machines);
}

function sameAxis(a: string[] | null, b: string[] | null): boolean {
  if (a === null || b === null) return a === b;
  return a.length === b.length && a.every((name) => b.includes(name));
}

/**
 * Which axis keeps this resource dormant *here*, or null when it is active.
 *
 * The machine axis is reported first, exactly as the API does: a resource
 * dormant on this whole machine is a different thing to explain than one
 * dormant for a particular agent, and it is the answer the user is more likely
 * to be looking for.
 *
 * Both axes are only judged on evidence. An unknown local machine id, or an
 * agent list that has not loaded, yields *no* verdict rather than a wrong one —
 * claiming a resource is dormant because a query is still in flight would be
 * worse than saying nothing.
 */
export function excludedAxis(
  scope: Scope | null,
  { machineId, agents }: { machineId: string | null; agents: string[] },
): ExclusionAxis | null {
  if (scope === null) return null;
  if (scope.machines !== null && machineId !== null && !scope.machines.includes(machineId)) {
    return "machine";
  }
  if (scope.agents !== null) {
    const namesNobody = scope.agents.length === 0;
    const namesNobodyHere =
      agents.length > 0 && !scope.agents.some((name) => agents.includes(name));
    if (namesNobody || namesNobodyHere) return "agent";
  }
  return null;
}
