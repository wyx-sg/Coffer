// src/lib/providers/usedBy.test.ts — the Used-by rule matches the agent Model tab's pick of the active provider.
import { describe, expect, test } from "vitest";

import type { AgentOut } from "@/lib/api/agents";
import type { Provider } from "@/lib/api/providers";
import { activeProviderFor, isInUse, providerUsedBy } from "./usedBy";

const provider = (uid: string, over: Partial<Provider> = {}): Provider => ({
  uid,
  name: uid,
  title: null,
  protocol: "openai",
  base_url: "https://gw/v1",
  credential_ref: `provider/${uid}`,
  local_runtime: null,
  compatible_agents: ["codex"],
  is_active: false,
  internal_default: false,
  transcribe_default: false,
  fallback: true,
  models: [],
  enabled: true,
  description: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  ...over,
});

const agent = (type: "claude_code" | "codex", model: string | null): AgentOut =>
  ({ uid: `a-${type}`, type, name: type, display_name: type, model }) as AgentOut;

describe("providerUsedBy", () => {
  test("an agent runs on the first enabled, active provider that reaches it", () => {
    const a = provider("a", { is_active: true });
    const b = provider("b", { is_active: true });
    const off = provider("off", { is_active: true, enabled: false });
    const codex = agent("codex", "gpt-5-codex");
    expect(activeProviderFor(codex, [off, a, b])?.uid).toBe("a");
    expect(providerUsedBy(a, [off, a, b], [codex]).agents).toEqual([
      { agent: codex, model: "gpt-5-codex" },
    ]);
    expect(providerUsedBy(b, [off, a, b], [codex]).agents).toEqual([]);
    expect(providerUsedBy(off, [off, a, b], [codex]).agents).toEqual([]);
  });

  test("a provider that does not reach the agent's type is not its provider", () => {
    const p = provider("p", { is_active: true, compatible_agents: ["claude_code"] });
    expect(providerUsedBy(p, [p], [agent("codex", "x")]).agents).toEqual([]);
  });

  test("an inactive provider carries no agent", () => {
    const p = provider("p");
    expect(providerUsedBy(p, [p], [agent("codex", "x")]).agents).toEqual([]);
  });

  test("Coffer's engine and speech to text follow their flags and models", () => {
    const p = provider("p", { internal_default: true, transcribe_default: true });
    const use = providerUsedBy(p, [p], [], { model: "gpt-5-mini", transcribe_model: "whisper-1" });
    expect(use.engine).toEqual({ model: "gpt-5-mini" });
    expect(use.transcribe).toEqual({ model: "whisper-1" });
    expect(isInUse(use)).toBe(true);
  });

  test("an unused provider is not in use", () => {
    const p = provider("p");
    const use = providerUsedBy(p, [p], [agent("codex", "x")], null);
    expect(use).toEqual({ agents: [], engine: null, transcribe: null });
    expect(isInUse(use)).toBe(false);
  });
});
