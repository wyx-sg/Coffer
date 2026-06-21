import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { AgentOverviewTab } from "./AgentOverviewTab";
import type { AgentOut } from "@/lib/api/agents";
import type { Provider } from "@/lib/api/providers";

vi.mock("@/lib/hooks/useProviders", () => ({
  useProviders: vi.fn(),
  useActivateProvider: vi.fn(),
  useUpdateProvider: vi.fn(),
}));
vi.mock("@/lib/hooks/useModelIntrospection", () => ({ useListProviderModels: vi.fn() }));

import {
  useActivateProvider,
  useProviders,
  useUpdateProvider,
} from "@/lib/hooks/useProviders";
import { useListProviderModels } from "@/lib/hooks/useModelIntrospection";

const useProvidersMock = useProviders as unknown as ReturnType<typeof vi.fn>;
const useActivateMock = useActivateProvider as unknown as ReturnType<typeof vi.fn>;
const useUpdateMock = useUpdateProvider as unknown as ReturnType<typeof vi.fn>;
const useListMock = useListProviderModels as unknown as ReturnType<typeof vi.fn>;

const activateMutate = vi.fn();
const updateMutate = vi.fn();

const agent: AgentOut = {
  name: "my-claude",
  type: "claude_code",
  config_dir: "/home/me/.claude",
  description: null,
  created_at: "",
  updated_at: "",
};

function makeConn(over: Partial<Provider> = {}): Provider {
  return {
    name: "official",
    wire_format: "anthropic",
    base_url: "https://api.anthropic.com",
    credential_ref: "ref",
    model: "claude-opus-4-8",
    fast_model: "claude-haiku-4-5",
    wire_api: "chat",
    is_active: true,
    internal_default: false,
    enabled: true,
    description: null,
    created_at: "",
    updated_at: "",
    ...over,
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
  useUpdateMock.mockReturnValue({ mutate: updateMutate, isPending: false });
  useListMock.mockReturnValue({ mutate: vi.fn() });
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
        makeConn({ name: "kimi", wire_format: "anthropic", is_active: false }),
        // an openai connection must NOT appear for a claude_code agent
        makeConn({ name: "gpt", wire_format: "openai", is_active: false }),
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

  test("the model dropdown offers the active connection's model + fast_model and a custom option", () => {
    useProvidersMock.mockReturnValue({ data: [makeConn({ is_active: true })] });
    render(<AgentOverviewTab agent={agent} />);
    const options = openSelectOptions(/^model$/i);
    expect(options).toContain("claude-opus-4-8");
    expect(options).toContain("claude-haiku-4-5");
    expect(options.some((o) => /custom/i.test(o))).toBe(true);
  });

  test("selecting a model patches the active connection (re-projects the agent model)", () => {
    useProvidersMock.mockReturnValue({ data: [makeConn({ is_active: true })] });
    render(<AgentOverviewTab agent={agent} />);
    openSelectOptions(/^model$/i);
    fireEvent.click(screen.getByRole("option", { name: "claude-haiku-4-5" }));
    expect(updateMutate).toHaveBeenCalledWith({
      name: "official",
      patch: { model: "claude-haiku-4-5" },
    });
  });

  test("the custom model option reveals a free-text input that patches the connection", () => {
    useProvidersMock.mockReturnValue({ data: [makeConn({ is_active: true })] });
    render(<AgentOverviewTab agent={agent} />);
    openSelectOptions(/^model$/i);
    fireEvent.click(screen.getByRole("option", { name: /custom/i }));
    const input = screen.getByLabelText(/custom model id/i);
    fireEvent.change(input, { target: { value: "claude-sonnet-4-6" } });
    fireEvent.blur(input);
    expect(updateMutate).toHaveBeenCalledWith({
      name: "official",
      patch: { model: "claude-sonnet-4-6" },
    });
  });

  test("with no compatible connection, points the user to Settings", () => {
    useProvidersMock.mockReturnValue({ data: [makeConn({ wire_format: "openai" })] });
    render(<AgentOverviewTab agent={agent} />);
    expect(screen.getByText(/no connection for this agent/i)).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: /connection/i })).not.toBeInTheDocument();
  });
});
