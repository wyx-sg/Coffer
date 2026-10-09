// src/lib/hooks/useAgentConnectionDraft.test.tsx
//
// The Change model dialog's draft, driven through the hook with a real query
// cache and only `call` (the network) faked: what makes a draft dirty and
// reviewable, the request it builds, and Coffer's tier prefill.
import type { PropsWithChildren } from "react";
import { beforeEach, describe, expect, test } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { fakeApi } from "@/test/fakeApi";
import type { AgentOut } from "@/lib/api/agents";
import type { AgentModel } from "@/lib/api/agentModels";
import type { Provider, ProviderModel } from "@/lib/api/providers";
import { BUILTIN, useAgentConnectionDraft } from "./useAgentConnectionDraft";

const call = fakeApi();

const AGENT: AgentOut = {
  uid: "a-claude",
  name: "claude-code",
  type: "claude_code",
  config_dir: "/home/me/.claude",
  display_name: "Claude Code",
  model: null,
  tier_models: null,
  version: null,
  install_handoff: null,
  connection_uid: null,
  state: "installed_active",
  created_at: "",
  updated_at: "",
};

const text = (...ids: string[]): ProviderModel[] => ids.map((id) => ({ id, modality: "text" }));

function conn(name: string, over: Partial<Provider> = {}): Provider {
  return {
    uid: `u-${name}`,
    name,
    protocol: "anthropic",
    base_url: "https://api.example.com",
    anthropic_base_url: null,
    secret_ref: "ref",
    title: null,
    transcribe_default: false,
    models: [],
    enabled: true,
    description: null,
    local_runtime: null,
    compatible_agents: ["claude_code", "codex"],
    served_agents: ["claude_code", "codex"],
    created_at: "",
    updated_at: "",
    ...over,
  };
}

function serve(providers: Provider[], catalogue: AgentModel[] = []) {
  call.mockImplementation(async (path: string, opts?: { method?: string }) => {
    if (path === "/providers") return { providers };
    if (path.startsWith("/agent-providers/")) return { models: catalogue };
    if (path === "/models/test-connection") return { ok: true, message: "ok" };
    if (opts?.method === "PATCH") return AGENT;
    if (path.endsWith("/activate")) return {};
    throw new Error(`unexpected ${path}`);
  });
}

async function setup(agent: AgentOut, providers: Provider[], catalogue?: AgentModel[]) {
  serve(providers, catalogue);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  const hook = renderHook(() => useAgentConnectionDraft(agent), { wrapper });
  await waitFor(() => expect(hook.result.current.loading).toBe(false));
  return hook;
}

beforeEach(() => {
  call.mockReset();
});

describe("useAgentConnectionDraft", () => {
  test("starts clean on the applied state; picking a provider makes it reviewable", async () => {
    const { result } = await setup(AGENT, [conn("gw", { models: text("m1", "m2") })]);
    expect(result.current.draftConn).toBe(BUILTIN);
    expect(result.current.dirty).toBe(false);
    expect(result.current.canReview).toBe(false);

    act(() => result.current.pickConnection("u-gw"));
    expect(result.current.draftModel).toBe("m1");
    expect(result.current.canReview).toBe(true);
    expect(result.current.request).toMatchObject({
      agent_type: "claude_code",
      connection_uid: "u-gw",
      model: "m1",
    });
  });

  test("Claude Code sends model and every tier; the built-in login sends none", async () => {
    const { result } = await setup(AGENT, [
      conn("gw", { models: text("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5") }),
    ]);
    act(() => result.current.pickConnection("u-gw"));
    expect(result.current.request).toEqual({
      agent_type: "claude_code",
      connection_uid: "u-gw",
      model: "claude-opus-5-5",
      tier_models: {
        opus: "claude-opus-5-5",
        sonnet: "claude-sonnet-5-5",
        haiku: "claude-haiku-5",
      },
    });
    act(() => result.current.pickConnection(BUILTIN));
    expect(result.current.request).toMatchObject({
      connection_uid: null,
      model: null,
      tier_models: null,
    });
  });

  test("Codex has no tiers", async () => {
    const codex: AgentOut = { ...AGENT, uid: "a-codex", type: "codex" };
    const { result } = await setup(codex, [
      conn("oa", { protocol: "openai", models: text("gpt-5") }),
    ]);
    expect(result.current.showTiers).toBe(false);
    act(() => result.current.pickConnection("u-oa"));
    expect(result.current.request).toMatchObject({
      model: "gpt-5",
      tier_models: null,
    });
  });

  test("a local runtime pins every tier to the Model; an edited tier can be changed", async () => {
    const { result } = await setup(AGENT, [
      conn("ollama", {
        base_url: "http://127.0.0.1:11434",
        models: text("qwen-coder", "claude-haiku-ish"),
      }),
    ]);
    act(() => result.current.pickConnection("u-ollama"));
    expect(result.current.draftTiers).toEqual({
      opus: "qwen-coder",
      sonnet: "qwen-coder",
      haiku: "qwen-coder",
    });
    act(() => result.current.pickTier("haiku", "claude-haiku-ish"));
    expect(result.current.draftTiers.haiku).toBe("claude-haiku-ish");
    expect(result.current.tiersAreSuggested).toBe(false);
  });

  test("a pointer to a connection that no longer reaches the agent reads as the built-in login", async () => {
    const agent: AgentOut = { ...AGENT, model: "m1", connection_uid: "u-gw" };
    const { result } = await setup(agent, [conn("gw", { enabled: false, models: text("m1") })]);
    expect(result.current.appliedConn).toBe(BUILTIN);
    expect(result.current.draftConn).toBe(BUILTIN);
  });

  test("an applied binding is the starting draft; changing the model makes it dirty", async () => {
    const agent: AgentOut = {
      ...AGENT,
      model: "m1",
      tier_models: { opus: "m1", sonnet: "m1", haiku: "m1" },
      connection_uid: "u-gw",
    };
    const { result } = await setup(agent, [conn("gw", { models: text("m1", "m2") })]);
    expect(result.current.draftConn).toBe("u-gw");
    expect(result.current.dirty).toBe(false);
    act(() => result.current.pickModel("m2"));
    expect(result.current.dirty).toBe(true);
  });
});
