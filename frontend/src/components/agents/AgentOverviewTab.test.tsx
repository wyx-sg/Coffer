import { beforeEach, describe, expect, test, vi } from "vitest";

import { acceptance } from "@/test/acceptance";
import { fireEvent, render, screen } from "@testing-library/react";

import { AgentOverviewTab } from "./AgentOverviewTab";
import type { AgentOut } from "@/lib/api/agents";
import type { Provider, ProviderModel } from "@/lib/api/providers";

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
    // No curated model set by default — the picker introspects the endpoint.
    models: [] as ProviderModel[],
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

/** Curated/introspected entries for chat ids — the common `text` case. */
function text(...ids: string[]): ProviderModel[] {
  return ids.map((id) => ({ id, modality: "text" as const }));
}

function openSelectOptions(triggerName: RegExp): string[] {
  const trigger = screen.getByRole("combobox", { name: triggerName });
  fireEvent.keyDown(trigger, { key: "ArrowDown" });
  return screen.getAllByRole("option").map((o) => o.textContent ?? "");
}

/** Like `openSelectOptions` but tolerates an EMPTY dropdown, and closes it
 *  again so a second picker can be inspected in the same test. */
function peekSelectOptions(triggerName: RegExp): string[] {
  const trigger = screen.getByRole("combobox", { name: triggerName });
  fireEvent.keyDown(trigger, { key: "ArrowDown" });
  const opts = screen.queryAllByRole("option").map((o) => o.textContent ?? "");
  fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
  return opts;
}

const confirmBtn = () => screen.getByRole("button", { name: /confirm switch/i });
const testBtn = () => screen.getByRole("button", { name: /test connection/i });

beforeEach(() => {
  vi.clearAllMocks();
  useActivateMock.mockReturnValue({ mutate: activateMutate, isPending: false });
  useUseBuiltinMock.mockReturnValue({ mutate: useBuiltinMutate, isPending: false });
  // The model dropdown is populated by introspecting the connection (the
  // connection no longer carries a model — spec provider-switching E3); resolve its catalogue.
  useListMock.mockReturnValue({
    mutate: (_probe: unknown, opts?: { onSuccess?: (r: { models: ProviderModel[] }) => void }) =>
      opts?.onSuccess?.({ models: text("claude-opus-4-8", "claude-haiku-4-5") }),
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
    const options = openSelectOptions(/provider/i);
    expect(options).toContain("official");
    expect(options).toContain("kimi");
    expect(options).not.toContain("gpt");
  });

  acceptance(
    "provider-switching",
    "the agent's model picker offers a fixed list without free-form entry",
    () => {
      useProvidersMock.mockReturnValue({ data: [makeConn({ is_active: true })] });
      render(<AgentOverviewTab agent={agent} />);
      const options = openSelectOptions(/^model$/i);
      // The connection's INTROSPECTED models, never its stored model field.
      expect(options).toContain("claude-opus-4-8");
      expect(options).toContain("claude-haiku-4-5");
      // No free-text escape hatch: a model id is chosen, never typed.
      expect(options.some((o) => /custom/i.test(o))).toBe(false);
      expect(screen.queryByRole("textbox")).toBeNull();
    },
  );

  test("picking a connection is a draft: it stages a default model, activates nothing", () => {
    useProvidersMock.mockReturnValue({ data: [agnes()] });
    useListMock.mockReturnValue({
      mutate: (_p: unknown, opts?: { onSuccess?: (r: { models: ProviderModel[] }) => void }) =>
        opts?.onSuccess?.({ models: text("agnes-2.0", "agnes-1.5-flash") }),
    });
    render(<AgentOverviewTab agent={agent} />);
    openSelectOptions(/provider/i);
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
      mutate: (_p: unknown, opts?: { onSuccess?: (r: { models: ProviderModel[] }) => void }) =>
        opts?.onSuccess?.({ models: text("agnes-2.0") }),
    });
    const { rerender } = render(<AgentOverviewTab agent={agent} />);
    openSelectOptions(/provider/i);
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
      mutate: (_p: unknown, opts?: { onSuccess?: (r: { models: ProviderModel[] }) => void }) =>
        opts?.onSuccess?.({ models: text("agnes-2.0") }),
    });
    const { rerender } = render(<AgentOverviewTab agent={agent} />);
    openSelectOptions(/provider/i);
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
      mutate: (_p: unknown, opts?: { onSuccess?: (r: { models: ProviderModel[] }) => void }) =>
        opts?.onSuccess?.({ models: text("agnes-2.0", "agnes-1.5-flash") }),
    });
    const { rerender } = render(<AgentOverviewTab agent={agent} />);
    openSelectOptions(/provider/i);
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
      mutate: (_p: unknown, opts?: { onSuccess?: (r: { models: ProviderModel[] }) => void }) =>
        opts?.onSuccess?.({ models: text("gpt-5-codex", "gpt-5") }),
    });
    const { rerender } = render(<AgentOverviewTab agent={codex} />);
    expect(screen.queryByRole("combobox", { name: /fast model/i })).not.toBeInTheDocument();
    openSelectOptions(/provider/i);
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
    openSelectOptions(/provider/i);
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

  test("the built-in login offers NO model control at all, only where to choose one", () => {
    // Nothing reads `agent.model` on the built-in login, so a model dropdown
    // there would write a field nobody reads — and curating a model list on an
    // AGENT is equally wrong: an agent has no audience. A channel does, and it
    // carries its own default model and allowed range (spec channels FR-071).
    // So this branch offers no control whatsoever, just the sentence saying
    // where the choice happens.
    useProvidersMock.mockReturnValue({ data: [] });
    render(<AgentOverviewTab agent={agent} />);
    expect(screen.queryByRole("combobox", { name: /^model$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: /fast model/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^save$/i })).not.toBeInTheDocument();
    expect(screen.getByText(/chosen per conversation/i)).toBeInTheDocument();
  });

  test("picking a connection brings the model slots back, enabled", () => {
    useProvidersMock.mockReturnValue({ data: [agnes()] });
    render(<AgentOverviewTab agent={agent} />);
    openSelectOptions(/provider/i);
    fireEvent.click(screen.getByRole("option", { name: "agnes" }));
    expect(screen.getByRole("combobox", { name: /^model$/i })).toBeEnabled();
    expect(screen.getByRole("combobox", { name: /fast model/i })).toBeEnabled();
  });

  // --- the connection's curated model set narrows the picker (spec provider-switching) ----
  // `models` on a connection is the set the user curated on its detail page.
  // Non-empty ⇒ it IS the catalogue (no endpoint introspection at all); empty
  // ⇒ "no restriction", and the options come from introspection as before.

  test("a curated connection supplies the model options and is never introspected", () => {
    const listMutate = vi.fn();
    useListMock.mockReturnValue({ mutate: listMutate });
    useProvidersMock.mockReturnValue({
      data: [agnes({ is_active: true, models: text("agnes-2.0", "agnes-1.5-flash") })],
    });
    render(<AgentOverviewTab agent={agent} />);

    const options = openSelectOptions(/^model$/i);
    expect(options).toEqual(["agnes-2.0", "agnes-1.5-flash"]);
    // The endpoint is never probed for its catalogue — the curated list is it.
    expect(listMutate).not.toHaveBeenCalled();
  });

  test("picking a curated connection stages its first model without introspecting", () => {
    const listMutate = vi.fn();
    useListMock.mockReturnValue({ mutate: listMutate });
    useProvidersMock.mockReturnValue({
      data: [
        makeConn({ name: "official", is_active: true }),
        agnes({ models: text("agnes-2.0", "agnes-1.5-flash") }),
      ],
    });
    render(<AgentOverviewTab agent={agent} />);
    openSelectOptions(/provider/i);
    fireEvent.click(screen.getByRole("option", { name: "agnes" }));

    expect(listMutate).not.toHaveBeenCalled();
    // The staged model came from the curated list, so Test is ready to run.
    fireEvent.click(testBtn());
    expect(testMutate).toHaveBeenCalledWith(
      expect.objectContaining({ model: "agnes-2.0", provider: "openai" }),
    );
  });

  test("an EMPTY curated set keeps today's behaviour: introspect the endpoint", () => {
    const listMutate = vi.fn(
      (_p: unknown, opts?: { onSuccess?: (r: { models: ProviderModel[] }) => void }) =>
        opts?.onSuccess?.({ models: text("agnes-2.0", "agnes-1.5-flash") }),
    );
    useListMock.mockReturnValue({ mutate: listMutate });
    useProvidersMock.mockReturnValue({ data: [agnes({ is_active: true, models: [] })] });
    render(<AgentOverviewTab agent={agent} />);

    const options = openSelectOptions(/^model$/i);
    expect(options).toContain("agnes-2.0");
    expect(options).toContain("agnes-1.5-flash");
    expect(listMutate).toHaveBeenCalled();
  });

  // --- the curated set is narrowed to modality `text` (spec provider-switching FR-030) ---
  // One endpoint answers for chat AND embeddings; the agent's binding is a CHAT
  // binding, so only `text` entries may be offered as the model it runs on.

  acceptance(
    "provider-switching",
    "a non-text curated model never reaches a chat model picker",
    () => {
      const listMutate = vi.fn();
      useListMock.mockReturnValue({ mutate: listMutate });
      useProvidersMock.mockReturnValue({
        data: [
          agnes({
            is_active: true,
            models: [
              { id: "agnes-2.0", modality: "text" },
              { id: "agnes-embed-3", modality: "embedding" },
            ],
          }),
        ],
      });
      render(<AgentOverviewTab agent={agent} />);

      // Both of Claude Code's slots are chat slots: the embedding id is offered
      // in neither, and the endpoint is still never probed.
      expect(peekSelectOptions(/^model$/i)).toEqual(["agnes-2.0"]);
      expect(peekSelectOptions(/fast model/i)).toEqual(["agnes-2.0"]);
      expect(listMutate).not.toHaveBeenCalled();
    },
  );

  test("a curated set with NO text entry offers no model and still never introspects", () => {
    // "Restricted" is decided by the WHOLE curated set, not by its text slice —
    // so curating only an embedding model means no chat model at all, rather
    // than silently falling back to the endpoint's full catalogue (mirrors the
    // daemon).
    const listMutate = vi.fn();
    useListMock.mockReturnValue({ mutate: listMutate });
    useProvidersMock.mockReturnValue({
      data: [agnes({ is_active: true, models: [{ id: "agnes-embed-3", modality: "embedding" }] })],
    });
    render(<AgentOverviewTab agent={agent} />);

    expect(peekSelectOptions(/^model$/i)).toEqual([]);
    expect(peekSelectOptions(/fast model/i)).toEqual([]);
    expect(listMutate).not.toHaveBeenCalled();
  });

  test("with no compatible connection, still defaults to the built-in connection", () => {
    useProvidersMock.mockReturnValue({ data: [makeConn({ protocol: "openai" })] });
    render(<AgentOverviewTab agent={agent} />);
    // No dead-end empty state: the connection dropdown always renders and
    // defaults to the built-in login (spec: built-in is the baseline).
    const combobox = screen.getByRole("combobox", { name: /provider/i });
    expect(combobox).toHaveTextContent(/built-in/i);
  });
});
