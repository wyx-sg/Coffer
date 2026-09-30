// src/lib/providers/usedBy.ts — who runs on a provider: agents (with their model), Coffer's engine, speech to text.
//
// An agent runs on provider P when P is the FIRST provider that is enabled,
// active and reaches the agent's type — exactly how the agent's Model tab
// (useAgentConnectionDraft) picks the active one, so the two pages never
// disagree. Coffer's engine uses P when P carries `internal_default`, speech
// to text when it carries `transcribe_default`; their models come from the
// internal-engine settings. The list is read-only: every entry is changed
// where it is set (the agent's Model tab, Settings › General).
import type { AgentOut } from "@/lib/api/agents";
import type { Provider } from "@/lib/api/providers";

interface AgentUse {
  agent: AgentOut;
  model: string | null;
}

export interface ProviderUse {
  agents: AgentUse[];
  /** Present when Coffer's engine runs on the provider. */
  engine: { model: string | null } | null;
  /** Present when speech to text runs on the provider. */
  transcribe: { model: string | null } | null;
}

export interface EngineModels {
  model: string | null;
  transcribe_model: string | null;
}

/** The provider an agent runs on right now, or null for its own login. */
export function activeProviderFor(
  agent: AgentOut,
  providers: readonly Provider[],
): Provider | null {
  return (
    providers.find(
      (p) => p.enabled && p.is_active && (p.compatible_agents ?? []).includes(agent.type),
    ) ?? null
  );
}

/** Every use of `provider`, in the Agents page's order (the `agents` order). */
export function providerUsedBy(
  provider: Provider,
  providers: readonly Provider[],
  agents: readonly AgentOut[],
  engine?: EngineModels | null,
): ProviderUse {
  return {
    agents: agents
      .filter((agent) => activeProviderFor(agent, providers)?.uid === provider.uid)
      .map((agent) => ({ agent, model: agent.model ?? null })),
    engine: provider.internal_default ? { model: engine?.model ?? null } : null,
    transcribe: provider.transcribe_default ? { model: engine?.transcribe_model ?? null } : null,
  };
}

/** Whether anything runs on the provider — the rule that blocks its delete. */
export function isInUse(use: ProviderUse): boolean {
  return use.agents.length > 0 || use.engine !== null || use.transcribe !== null;
}
