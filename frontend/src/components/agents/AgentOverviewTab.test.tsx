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
vi.mock("@/lib/hooks/useModelIntrospection", () => ({ useListProviderModels: vi.fn() }));
vi.mock("@/lib/hooks/useAgents", () => ({ usePatchAgent: vi.fn() }));

import { useActivateProvider, useProviders, useUseBuiltinProvider } from "@/lib/hooks/useProviders";
import { useListProviderModels } from "@/lib/hooks/useModelIntrospection";
import { usePatchAgent } from "@/lib/hooks/useAgents";

const useProvidersMock = useProviders as unknown as ReturnType<typeof vi.fn>;
const useActivateMock = useActivateProvider as unknown as ReturnType<typeof vi.fn>;
const useUseBuiltinMock = useUseBuiltinProvider as unknown as ReturnType<typeof vi.fn>;
const useListMock = useListProviderModels as unknown as ReturnType<typeof vi.fn>;
const usePatchAgentMock = usePatchAgent as unknown as ReturnType<typeof vi.fn>;

const activateMutate = vi.fn();
const useBuiltinMutate = vi.fn();
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

function openSelectOptions(triggerName: RegExp): string[] {
  const trigger = screen.getByRole("combobox", { name: triggerName });
  fireEvent.keyDown(trigger, { key: "ArrowDown" });
  return screen.getAllByRole("option").map((o) => o.textContent ?? "");
}

beforeEach(() => {
  vi.clearAllMocks();
  useActivateMock.mockReturnValue({ mutate: activateMutate, isPending: false });
  useUseBuiltinMock.mockReturnValue({ mutate: useBuiltinMutate, isPending: false });
  // The model dropdown is populated by introspecting the active connection (the
  // connection no longer carries a model — spec 011 E3); resolve its catalogue.
  useListMock.mockReturnValue({
    mutate: (_probe: unknown, opts?: { onSuccess?: (r: { models: string[] }) => void }) =>
      opts?.onSuccess?.({ models: ["claude-opus-4-8", "claude-haiku-4-5"] }),
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

  test("selecting another connection activates it for the agent", () => {
    useProvidersMock.mockReturnValue({
      data: [
        makeConn({ name: "official", is_active: true }),
        makeConn({ name: "kimi", is_active: false }),
      ],
    });
    render(<AgentOverviewTab agent={agent} />);
    openSelectOptions(/connection/i);
    fireEvent.click(screen.getByRole("option", { name: "kimi" }));
    expect(activateMutate).toHaveBeenCalledWith("kimi");
  });

  test("selecting Use built-in switches the agent back to its own login", () => {
    useProvidersMock.mockReturnValue({ data: [makeConn({ is_active: true })] });
    render(<AgentOverviewTab agent={agent} />);
    openSelectOptions(/connection/i);
    fireEvent.click(screen.getByRole("option", { name: /built-in/i }));
    expect(useBuiltinMutate).toHaveBeenCalledWith("anthropic");
    expect(activateMutate).not.toHaveBeenCalled();
  });

  test("the model dropdown offers the connection's introspected models", () => {
    useProvidersMock.mockReturnValue({ data: [makeConn({ is_active: true })] });
    render(<AgentOverviewTab agent={agent} />);
    const options = openSelectOptions(/^model$/i);
    expect(options).toContain("claude-opus-4-8");
    expect(options).toContain("claude-haiku-4-5");
  });

  test("selecting a model binds it on the agent then re-projects", () => {
    useProvidersMock.mockReturnValue({ data: [makeConn({ is_active: true })] });
    render(<AgentOverviewTab agent={agent} />);
    openSelectOptions(/^model$/i);
    fireEvent.click(screen.getByRole("option", { name: "claude-haiku-4-5" }));
    // Writes the per-agent binding (NOT the connection) …
    expect(patchAgentMutate).toHaveBeenCalledWith(
      { name: "my-claude", body: { model: "claude-haiku-4-5" } },
      expect.anything(),
    );
    // … then re-activates the connection to re-project from the new binding.
    expect(activateMutate).toHaveBeenCalledWith("official");
  });

  test("Claude Code exposes a fast-model slot that binds the fast model", () => {
    useProvidersMock.mockReturnValue({ data: [makeConn({ is_active: true })] });
    render(<AgentOverviewTab agent={agent} />);
    openSelectOptions(/fast model/i);
    fireEvent.click(screen.getAllByRole("option", { name: "claude-opus-4-8" })[0]);
    expect(patchAgentMutate).toHaveBeenCalledWith(
      { name: "my-claude", body: { fast_model: "claude-opus-4-8" } },
      expect.anything(),
    );
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
});
