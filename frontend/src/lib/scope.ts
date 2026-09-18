// frontend/src/lib/scope.ts
//
// Pure helpers over a resource's activation scope — the agents it reaches (ADR
// per-agent-resource-scope). They mirror `backend/coffer/domain/scope.py`,
// which is the authority; keep the two in step.
//
// A separate module from `hooks/useScope.ts` on purpose: these are functions,
// not hooks, and a test that mocks the hook module must not lose them with it.
import type { Scope } from "@/lib/hooks/useScope";

/** True when the two scopes name the same set of agents (by uid). */
export function sameScope(a: Scope | null, b: Scope | null): boolean {
  if (a === null || b === null) return a === b;
  return sameAgents(a.agents, b.agents);
}

function sameAgents(a: string[] | null, b: string[] | null): boolean {
  if (a === null || b === null) return a === b;
  return a.length === b.length && a.every((uid) => b.includes(uid));
}

/**
 * Whether this resource reaches nobody *here*: it is scoped to agents, and no
 * agent registered on this machine is among them. Both sides are agent UIDS —
 * the form a scope stores and the form an agent resource carries, so there is
 * one vocabulary and nothing to translate between.
 *
 * "Here" is the only question left to ask. Reach is machine-local — this vault
 * stores it and never converges it with a remote — so a resource's scope is
 * always judged against the agents registered on the machine that is asking.
 *
 * Judged on evidence. An agent list that has not loaded yet yields `false`
 * rather than a wrong `true`: claiming a resource is dormant because a query is
 * still in flight would be worse than saying nothing. An explicitly empty list
 * is the one verdict that needs no evidence — it names nobody, anywhere.
 */
export function isDormantHere(scope: Scope | null, agentUids: string[]): boolean {
  if (scope === null || scope.agents === null) return false;
  if (scope.agents.length === 0) return true;
  return agentUids.length > 0 && !scope.agents.some((uid) => agentUids.includes(uid));
}
