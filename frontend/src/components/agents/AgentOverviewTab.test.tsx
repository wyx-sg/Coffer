import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { AgentOverviewTab } from "./AgentOverviewTab";
import type { AgentOut } from "@/lib/api/agents";
import type { Provider } from "@/lib/api/providers";

vi.mock("@/lib/hooks/useProviders", () => ({
  useProviders: vi.fn(),
  useActivateProvider: vi.fn(),
  useUseBuiltinProvider: vi.fn(),
}));
vi.mock("@/lib/hooks/useModelIntrospection", () => ({
  useListProviderModels: vi.fn(),
  useTestConnection: vi.fn(),
}));
vi.mock("@/lib/hooks/useAgents", () => ({ usePatchAgent: vi.fn() }));

import { useActivateProvider, useProviders, useUseBuiltinProvider } from "@/lib/hooks/useProviders";
import { useListProviderModels, useTestConnection } from "@/lib/hooks/useModelIntrospection";
import { usePatchAgent } from "@/lib/hooks/useAgents";

const useProvidersMock = useProviders as unknown as ReturnType<typeof vi.fn>;
const useActivateMock = useActivateProvider as unknown as ReturnType<typeof vi.fn>;
const useUseBuiltinMock = useUseBuiltinProvider as unknown as ReturnType<typeof vi.fn>;
const useListMock = useListProviderModels as unknown as ReturnType<typeof vi.fn>;
const useTestMock = useTestConnection as unknown as ReturnType<typeof vi.fn>;
const usePatchAgentMock = usePatchAgent as unknown as ReturnType<typeof vi.fn>;

const activateMutate = vi.fn();
const useBuiltinMutate = vi.fn();
const testMutate = vi.fn();
const testReset = vi.fn();
// Invoke onSuccess so the "re-project after binding" step (re-activate) runs.
const patchAgentMutate = vi.fn((_vars: unknown, opts?: { onSuccess?: () => void }) =>
  opts?.onSuccess?.(),
);

const agent: AgentOut = {
  name: "my-claude",
  type: "claude_code",
  config_dir: "/home/me/.claude",
  description: null,
  created_at: "",
  updated_at: "",
};

function makeConn(over: Partial<Provider> = {}): Provider {
  const merged = {
    name: "official",
    protocol: "anthropic" as Provider["protocol"],
    base_url: "https://api.anthropic.com",
    credential_ref: "ref",
    is_active: true,
    internal_default: false,
    enabled: true,
    description: null,
    created_at: "",
    updated_at: "",
    ...over,
  };
  // Default the compatible set from the wire (mirrors the backend default) unless
  // the test pins it explicitly — the Overview picker filters on this set.
  return {
    ...merged,
    compatible_agents:
      over.compatible_agents ?? (merged.protocol === "openai" ? ["codex"] : ["claude_code"]),
  };
}

// agnes: an openai gateway routed to Claude Code, serving its own model ids.
function agnes(over: Partial<Provider> = {}): Provider {
  return makeConn({
    name: "agnes",
    protocol: "openai",
    base_url: "https://apihub.agnes-ai.com/v1",
    is_active: false,
    compatible_agents: ["claude_code"],
    ...over,
  });
}

function passingTest() {
  useTestMock.mockReturnValue({
    mutate: testMutate,
    reset: testReset,
    isPending: false,
    data: { ok: true, message: "OK" },
  });
}

function openSelectOptions(triggerName: RegExp): string[] {
  const trigger = screen.getByRole("combobox", { name: triggerName });
  fireEvent.keyDown(trigger, { key: "ArrowDown" });
  return screen.getAllByRole("option").map((o) => o.textContent ?? "");
}

const confirmBtn = () => screen.getByRole("button", { name: /confirm switch/i });
const testBtn = () => screen.getByRole("button", { name: /test connection/i });

beforeEach(() => {
  vi.clearAllMocks();
  useActivateMock.mockReturnValue({ mutate: activateMutate, isPending: false });
  useUseBuiltinMock.mockReturnValue({ mutate: useBuiltinMutate, isPending: false });
  // The model dropdown is populated by introspecting the connection (the
  // connection no longer carries a model — spec 011 E3); resolve its catalogue.
  useListMock.mockReturnValue({
    mutate: (_probe: unknown, opts?: { onSuccess?: (r: { models: string[] }) => void }) =>
      opts?.onSuccess?.({ models: ["claude-opus-4-8", "claude-haiku-4-5"] }),
  });
  // Default: no test run yet.
  useTestMock.mockReturnValue({
    mutate: testMutate,
    reset: testReset,
    isPending: false,
    data: undefined,
  });
  usePatchAgentMock.mockReturnValue({ mutate: patchAgentMutate, isPending: false });
  useProvidersMock.mockReturnValue({ data: [] });
});

describe("AgentOverviewTab", () => {
  test("shows the agent type and config directory", () => {
    render(<AgentOverviewTab agent={agent} />);
    expect(screen.getByText("claude_code")).toBeInTheDocument();
    expect(screen.getByText("/home/me/.claude")).toBeInTheDocument();
  });

  test("lists only wire-compatible connections for the agent", () => {
    useProvidersMock.mockReturnValue({
      data: [
        makeConn({ name: "official", is_active: true }),
        makeConn({ name: "kimi", protocol: "anthropic", is_active: false }),
        makeConn({ name: "gpt", protocol: "openai", is_active: false }),
      ],
    });
    render(<AgentOverviewTab agent={agent} />);
    const options = openSelectOptions(/connection/i);
    expect(options).toContain("official");
    expect(options).toContain("kimi");
    expect(options).not.toContain("gpt");
  });

  test("the model dropdown offers the connection's introspected models", () => {
    useProvidersMock.mockReturnValue({ data: [makeConn({ is_active: true })] });
    render(<AgentOverviewTab agent={agent} />);
    const options = openSelectOptions(/^model$/i);
    expect(options).toContain("claude-opus-4-8");
    expect(options).toContain("claude-haiku-4-5");
  });

  test("picking a connection is a draft: it stages a default model, activates nothing", () => {
    useProvidersMock.mockReturnValue({ data: [agnes()] });
    useListMock.mockReturnValue({
      mutate: (_p: unknown, opts?: { onSuccess?: (r: { models: string[] }) => void }) =>
        opts?.onSuccess?.({ models: ["agnes-2.0", "agnes-1.5-flash"] }),
    });
    render(<AgentOverviewTab agent={agent} />);
    openSelectOptions(/connection/i);
    fireEvent.click(screen.getByRole("option", { name: "agnes" }));
    // Nothing is projected on a mere pick …
    expect(activateMutate).not.toHaveBeenCalled();
    expect(patchAgentMutate).not.toHaveBeenCalled();
    expect(useBuiltinMutate).not.toHaveBeenCalled();
    // … but a default model is staged (the Test button needs a model to enable).
    expect(testBtn()).toBeEnabled();
  });

  test("confirm stays disabled until the connection test passes", () => {
    useProvidersMock.mockReturnValue({
      data: [makeConn({ name: "official", is_active: true }), agnes()],
    });
    useListMock.mockReturnValue({
      mutate: (_p: unknown, opts?: { onSuccess?: (r: { models: string[] }) => void }) =>
        opts?.onSuccess?.({ models: ["agnes-2.0"] }),
    });
    const { rerender } = render(<AgentOverviewTab agent={agent} />);
    openSelectOptions(/connection/i);
    fireEvent.click(screen.getByRole("option", { name: "agnes" }));
    expect(confirmBtn()).toBeDisabled();
    passingTest();
    rerender(<AgentOverviewTab agent={agent} />);
    expect(confirmBtn()).toBeEnabled();
  });

  test("a failed test keeps confirm disabled and shows the error message", () => {
    useProvidersMock.mockReturnValue({
      data: [makeConn({ name: "official", is_active: true }), agnes()],
    });
    useListMock.mockReturnValue({
      mutate: (_p: unknown, opts?: { onSuccess?: (r: { models: string[] }) => void }) =>
        opts?.onSuccess?.({ models: ["agnes-2.0"] }),
    });
    const { rerender } = render(<AgentOverviewTab agent={agent} />);
    openSelectOptions(/connection/i);
    fireEvent.click(screen.getByRole("option", { name: "agnes" }));
    useTestMock.mockReturnValue({
      mutate: testMutate,
      reset: testReset,
      isPending: false,
      data: { ok: false, message: "invalid key" },
    });
    rerender(<AgentOverviewTab agent={agent} />);
    expect(confirmBtn()).toBeDisabled();
    expect(screen.getByText("invalid key")).toBeInTheDocument();
  });

  test("test then confirm binds both model slots and activates the connection", () => {
    useProvidersMock.mockReturnValue({
      data: [makeConn({ name: "official", is_active: true }), agnes()],
    });
    useListMock.mockReturnValue({
      mutate: (_p: unknown, opts?: { onSuccess?: (r: { models: string[] }) => void }) =>
        opts?.onSuccess?.({ models: ["agnes-2.0", "agnes-1.5-flash"] }),
    });
    const { rerender } = render(<AgentOverviewTab agent={agent} />);
    openSelectOptions(/connection/i);
    fireEvent.click(screen.getByRole("option", { name: "agnes" }));
    fireEvent.click(testBtn());
    // Test probes the drafted connection + staged model (test-connection needs a model).
    expect(testMutate).toHaveBeenCalledWith({
      provider: "openai",
      model: "agnes-2.0",
      base_url: "https://apihub.agnes-ai.com/v1",
      credential_ref: "ref",
    });
    passingTest();
    rerender(<AgentOverviewTab agent={agent} />);
    fireEvent.click(confirmBtn());
    // Confirm PATCHes both slots (default = first model) then activates.
    expect(patchAgentMutate).toHaveBeenCalledWith(
      { name: "my-claude", body: { model: "agnes-2.0", fast_model: "agnes-2.0" } },
      expect.anything(),
    );
    expect(activateMutate).toHaveBeenCalledWith("agnes");
  });

  test("Codex confirm binds only the model (no fast slot)", () => {
    const codex: AgentOut = { ...agent, name: "my-codex", type: "codex" };
    useProvidersMock.mockReturnValue({ data: [agnes({ compatible_agents: ["codex"] })] });
    useListMock.mockReturnValue({
      mutate: (_p: unknown, opts?: { onSuccess?: (r: { models: string[] }) => void }) =>
        opts?.onSuccess?.({ models: ["gpt-5-codex", "gpt-5"] }),
    });
    const { rerender } = render(<AgentOverviewTab agent={codex} />);
    expect(screen.queryByRole("combobox", { name: /fast model/i })).not.toBeInTheDocument();
    openSelectOptions(/connection/i);
    fireEvent.click(screen.getByRole("option", { name: "agnes" }));
    fireEvent.click(testBtn());
    passingTest();
    rerender(<AgentOverviewTab agent={codex} />);
    fireEvent.click(confirmBtn());
    expect(patchAgentMutate).toHaveBeenCalledWith(
      { name: "my-codex", body: { model: "gpt-5-codex" } },
      expect.anything(),
    );
    expect(activateMutate).toHaveBeenCalledWith("agnes");
  });

  test("switching to built-in confirms without a test", () => {
    useProvidersMock.mockReturnValue({ data: [makeConn({ name: "official", is_active: true })] });
    render(<AgentOverviewTab agent={agent} />);
    openSelectOptions(/connection/i);
    fireEvent.click(screen.getByRole("option", { name: /built-in/i }));
    // Built-in needs no endpoint test — confirm is enabled straight away.
    expect(confirmBtn()).toBeEnabled();
    fireEvent.click(confirmBtn());
    expect(useBuiltinMutate).toHaveBeenCalledWith("anthropic");
    expect(activateMutate).not.toHaveBeenCalled();
    expect(patchAgentMutate).not.toHaveBeenCalled();
  });

  test("confirm is disabled when the draft matches the applied state", () => {
    useProvidersMock.mockReturnValue({ data: [makeConn({ is_active: true })] });
    render(<AgentOverviewTab agent={agent} />);
    // No change staged yet → nothing to confirm.
    expect(confirmBtn()).toBeDisabled();
  });

  test("Codex has no fast-model slot", () => {
    const codex: AgentOut = { ...agent, name: "my-codex", type: "codex" };
    useProvidersMock.mockReturnValue({
      data: [makeConn({ protocol: "openai", is_active: true })],
    });
    render(<AgentOverviewTab agent={codex} />);
    expect(screen.queryByRole("combobox", { name: /fast model/i })).not.toBeInTheDocument();
  });

  test("with no compatible connection, still defaults to the built-in connection", () => {
    useProvidersMock.mockReturnValue({ data: [makeConn({ protocol: "openai" })] });
    render(<AgentOverviewTab agent={agent} />);
    // No dead-end empty state: the connection dropdown always renders and
    // defaults to the built-in login (spec: built-in is the baseline).
    const combobox = screen.getByRole("combobox", { name: /connection/i });
    expect(combobox).toHaveTextContent(/built-in/i);
  });

  test("a type without connection support shows the uniform note, no picker", () => {
    // FR-003a / ADR-042 presentation amendment: cursor renders the neutral
    // "not supported" note with its reason instead of a functional-looking
    // picker that can never offer a compatible connection.
    const cursor: AgentOut = {
      ...agent,
      name: "cursor",
      type: "cursor",
      config_dir: "/home/me/.cursor",
      capabilities: { plugins: false, transcripts: false, connections: false },
    };
    render(<AgentOverviewTab agent={cursor} />);
    expect(screen.getByText(/does not support llm connections/i)).toBeInTheDocument();
    expect(screen.getByText(/locked to cursor's own backend/i)).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: /connection/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /confirm/i })).not.toBeInTheDocument();
  });
});
