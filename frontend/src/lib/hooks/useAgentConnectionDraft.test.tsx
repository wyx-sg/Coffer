// src/lib/hooks/useAgentConnectionDraft.test.tsx
//
// The Model tab's draft → test → confirm state machine, driven through the
// hook with a real query cache and only `call` (the network) faked: what makes
// a draft dirty, the test-before-confirm rule, which binding fields a confirm
// PATCHes, where Effort's levels come from, and Coffer's tier prefill.
import type { PropsWithChildren } from "react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { AgentOut } from "@/lib/api/agents";
import type { AgentModel } from "@/lib/api/agentModels";
import type { Provider, ProviderModel } from "@/lib/api/providers";
import { BUILTIN, useAgentConnectionDraft } from "./useAgentConnectionDraft";

const call = vi.fn();
vi.mock("@/lib/api/call", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/call")>();
  return { ...actual, call: (...args: unknown[]) => call(...args) };
});

const AGENT: AgentOut = {
  uid: "a-claude",
  name: "claude-code",
  type: "claude_code",
  config_dir: "/home/me/.claude",
  display_name: "Claude Code",
  model: null,
  effort: null,
  tier_models: null,
  wire_api: null,
  version: null,
  install_handoff: null,
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
    secret_ref: "ref",
    is_active: false,
    title: null,
    internal_default: false,
    transcribe_default: false,
    fallback: true,
    models: [],
    enabled: true,
    description: null,
    local_runtime: null,
    compatible_agents: ["claude_code", "codex"],
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

async function testAndConfirm(result: { current: ReturnType<typeof useAgentConnectionDraft> }) {
  act(() => result.current.runTest());
  await waitFor(() => expect(result.current.canConfirm).toBe(true));
  act(() => result.current.confirm());
  await waitFor(() =>
    expect(call.mock.calls.some(([p]) => String(p).endsWith("/activate"))).toBe(true),
  );
  const patch = call.mock.calls.find(([, o]) => (o as { method?: string })?.method === "PATCH");
  return (patch?.[1] as { body: Record<string, unknown> }).body;
}

beforeEach(() => {
  call.mockReset();
});

describe("useAgentConnectionDraft", () => {
  test("starts clean on the applied state and needs a passing test before confirm", async () => {
    const { result } = await setup(AGENT, [conn("gw", { models: text("m1", "m2") })]);
    expect(result.current.draftConn).toBe(BUILTIN);
    expect(result.current.dirty).toBe(false);

    act(() => result.current.pickConnection("u-gw"));
    expect(result.current.draftModel).toBe("m1");
    expect(result.current.dirty).toBe(true);
    expect(result.current.canConfirm).toBe(false);

    act(() => result.current.runTest());
    await waitFor(() => expect(result.current.canConfirm).toBe(true));
    // A model change invalidates the test.
    act(() => result.current.pickModel("m2"));
    expect(result.current.canConfirm).toBe(false);
  });

  test("Claude Code confirm PATCHes model, effort and tier_models — never fast_model", async () => {
    const { result } = await setup(
      AGENT,
      [conn("gw", { models: text("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5") })],
      [
        {
          id: "claude-opus-5-5",
          label: "Opus",
          description: "",
          efforts: ["low", "high"],
          default_effort: null,
        },
      ],
    );
    act(() => result.current.pickConnection("u-gw"));
    expect(result.current.effortLevels).toEqual(["low", "high"]);
    act(() => result.current.pickEffort("high"));
    const body = await testAndConfirm(result);
    expect(body).toEqual({
      model: "claude-opus-5-5",
      effort: "high",
      tier_models: {
        opus: "claude-opus-5-5",
        sonnet: "claude-sonnet-5-5",
        haiku: "claude-haiku-5",
      },
    });
    expect(body).not.toHaveProperty("fast_model");
  });

  test("Codex confirm sends no tier_models, and an unset effort clears with null", async () => {
    const codex: AgentOut = { ...AGENT, uid: "a-codex", type: "codex", effort: "high" };
    const { result } = await setup(codex, [
      conn("oa", { protocol: "openai", models: text("gpt-5") }),
    ]);
    expect(result.current.showTiers).toBe(false);
    act(() => result.current.pickConnection("u-oa"));
    const body = await testAndConfirm(result);
    expect(body).toEqual({ model: "gpt-5", effort: null });
  });

  test("the connection's recorded levels win over the agent's catalogue", async () => {
    const { result } = await setup(
      AGENT,
      [
        conn("gw", {
          models: [{ id: "gpt-x", modality: "text", effort_levels: ["low", "medium"] }],
        }),
      ],
      [{ id: "gpt-x", label: "", description: "", efforts: ["high"], default_effort: null }],
    );
    act(() => result.current.pickConnection("u-gw"));
    expect(result.current.effortLevels).toEqual(["low", "medium"]);
  });

  test("a local runtime pins every tier to the Model; Reset puts an edited tier back", async () => {
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
    act(() => result.current.resetTiers());
    expect(result.current.draftTiers.haiku).toBe("qwen-coder");
  });

  test("an applied binding is the starting draft, and Discard returns to it", async () => {
    const agent: AgentOut = {
      ...AGENT,
      model: "m1",
      effort: "low",
      tier_models: { opus: "m1", sonnet: "m1", haiku: "m1" },
    };
    const { result } = await setup(agent, [
      conn("gw", { is_active: true, models: text("m1", "m2") }),
    ]);
    expect(result.current.draftConn).toBe("u-gw");
    expect(result.current.draftEffort).toBe("low");
    expect(result.current.dirty).toBe(false);
    act(() => result.current.pickModel("m2"));
    expect(result.current.dirty).toBe(true);
    act(() => result.current.discard());
    expect(result.current.draftModel).toBe("m1");
    expect(result.current.dirty).toBe(false);
  });
});
