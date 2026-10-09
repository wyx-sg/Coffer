// src/lib/providers/usedBy.test.ts — the Used-by rule reads the agent's `connection_uid`, as the agent Model tab does.
import { describe, expect, test } from "vitest";

import type { AgentOut } from "@/lib/api/agents";
import type { Provider } from "@/lib/api/providers";
import { activeProviderFor, isInUse, providerUsedBy } from "./usedBy";

const provider = (uid: string, over: Partial<Provider> = {}): Provider => ({
  uid,
  name: uid,
  protocol: "openai",
  base_url: "https://gw/v1",
  anthropic_base_url: null,
  secret_ref: `provider/${uid}`,
  local_runtime: null,
  compatible_agents: ["codex"],
  served_agents: ["codex"],
  transcribe_default: false,
  models: [],
  enabled: true,
  description: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  ...over,
});

const agent = (
  type: "claude_code" | "codex",
  model: string | null,
  connection_uid: string | null = null,
): AgentOut =>
  ({ uid: `a-${type}`, type, name: type, display_name: type, model, connection_uid }) as AgentOut;

describe("providerUsedBy", () => {
  test("an agent runs on the provider its record names", () => {
    const a = provider("a");
    const b = provider("b");
    const codex = agent("codex", "gpt-5-codex", "a");
    expect(activeProviderFor(codex, [b, a])?.uid).toBe("a");
    expect(providerUsedBy(a, [a, b], [codex]).agents).toEqual([
      { agent: codex, model: "gpt-5-codex" },
    ]);
    expect(providerUsedBy(b, [a, b], [codex]).agents).toEqual([]);
  });

  test("a pointer to a switched-off or missing provider means the agent's own login", () => {
    const off = provider("off", { enabled: false });
    const codex = agent("codex", "x", "off");
    expect(activeProviderFor(codex, [off])).toBeNull();
    expect(providerUsedBy(off, [off], [codex]).agents).toEqual([]);
    expect(activeProviderFor(agent("codex", "x", "gone"), [off])).toBeNull();
  });

  test("a provider that does not reach the agent's type is not its provider", () => {
    const p = provider("p", { compatible_agents: ["claude_code"] });
    expect(providerUsedBy(p, [p], [agent("codex", "x", "p")]).agents).toEqual([]);
  });

  test("an agent that names no connection is on its own login", () => {
    const p = provider("p");
    expect(providerUsedBy(p, [p], [agent("codex", "x")]).agents).toEqual([]);
  });

  test("speech to text follows its flag and model", () => {
    const p = provider("p", { transcribe_default: true });
    const use = providerUsedBy(p, [p], [], { transcribe_model: "whisper-1" });
    expect(use.transcribe).toEqual({ model: "whisper-1" });
    expect(isInUse(use)).toBe(true);
  });

  test("an unused provider is not in use", () => {
    const p = provider("p");
    const use = providerUsedBy(p, [p], [agent("codex", "x")], null);
    expect(use).toEqual({ agents: [], transcribe: null });
    expect(isInUse(use)).toBe(false);
  });
});
