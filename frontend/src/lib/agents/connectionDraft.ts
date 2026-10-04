// Pure helpers of the agent connection draft (see useAgentConnectionDraft).

import type { Provider } from "@/lib/api/providers";

// Radix forbids an empty value, so the "use built-in login" option is a token.
export const BUILTIN = "__builtin__";

export type Tier = "opus" | "sonnet" | "haiku" | "fable";
export type TierModels = Partial<Record<Tier, string>>;
const BASE_TIERS: Tier[] = ["opus", "sonnet", "haiku"];

/** A connection to a model runtime on this machine: detected as one, or on loopback. */
export function isLocal(conn: Provider | null): boolean {
  if (!conn) return false;
  if (conn.local_runtime) return true;
  try {
    const host = new URL(conn.base_url ?? "").hostname.replace(/^\[|\]$/g, "");
    return host === "localhost" || host === "127.0.0.1" || host === "::1";
  } catch {
    return false;
  }
}

/** The tiers a connection offers: Fable only when one of its models is a Fable. */
export function tiersFor(models: string[]): Tier[] {
  return models.some((m) => m.toLowerCase().includes("fable"))
    ? [...BASE_TIERS, "fable"]
    : BASE_TIERS;
}

/** Coffer's prefill (spec provider-switching "Suggest a model for each Claude
 *  Code tier"): the model whose id names the tier, else the Model; a local
 *  runtime pins every tier to the Model. */
export function suggestTiers(models: string[], model: string, local: boolean): TierModels {
  const out: TierModels = {};
  for (const tier of tiersFor(models)) {
    const match = local ? undefined : models.find((m) => m.toLowerCase().includes(tier));
    out[tier] = match ?? model;
  }
  return out;
}

export const tiersKey = (tiers: TierModels) => JSON.stringify(Object.entries(tiers).sort());
