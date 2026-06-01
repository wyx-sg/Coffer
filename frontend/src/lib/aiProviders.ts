// frontend/src/lib/aiProviders.ts — shared constants for the built-in agent's
// LLM provider config (spec 008). The provider key + model are GLOBAL: they are
// set once in Settings → AI and applied to the default built-in agent. Other
// built-in agents inherit them on create.

/**
 * The default / first built-in agent. Settings → AI reads & patches this one,
 * and new built-in agents copy its `model` + `credential_ref` so they inherit
 * the global provider configuration.
 */
export const DEFAULT_BUILTIN_AGENT = "coffer" as const;

/** A provider whose API key lives in the keychain under `ai/<id>`. */
export interface AiProvider {
  /** Provider id; also the model prefix before the first `:`. */
  id: string;
  /** Display label. */
  label: string;
  /** Whether this provider needs an API key (Ollama runs locally — none). */
  needsKey: boolean;
}

export const AI_PROVIDERS: AiProvider[] = [
  { id: "anthropic", label: "Anthropic", needsKey: true },
  { id: "openai", label: "OpenAI", needsKey: true },
  { id: "ollama", label: "Ollama", needsKey: false },
];

/** A few model presets to seed the model field. */
export const MODEL_PRESETS: string[] = [
  "anthropic:claude-sonnet-4-6",
  "anthropic:claude-opus-4-6",
  "openai:gpt-4o",
  "openai:gpt-4o-mini",
  "ollama:llama3",
];

/** The keychain ref a provider's API key is stored under. */
export function credentialRefFor(providerId: string): string {
  return `ai/${providerId}`;
}

/** Derive the provider id from a provider-qualified model string. */
export function providerFromModel(model: string): string {
  const idx = model.indexOf(":");
  return idx > 0 ? model.slice(0, idx) : model;
}
