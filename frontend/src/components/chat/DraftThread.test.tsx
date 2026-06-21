import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { acceptance } from "@/test/acceptance";
import { DraftThread } from "./DraftThread";
import type { AgentInfo } from "@/lib/api/chat";
import type { Provider } from "@/lib/api/providers";

// The model picker (and the no-connection empty state) read the providers list.
vi.mock("@/lib/hooks/useProviders", () => ({ useProviders: vi.fn() }));
vi.mock("@/lib/hooks/useModelIntrospection", () => ({
  useListProviderModels: () => ({ mutate: vi.fn() }),
}));

import { useProviders } from "@/lib/hooks/useProviders";
const useProvidersMock = useProviders as unknown as ReturnType<typeof vi.fn>;

const activeConnection = {
  name: "official",
  wire_format: "anthropic",
  base_url: "https://api.anthropic.com",
  credential_ref: "ref",
  model: "claude-opus-4-8",
  fast_model: null,
  wire_api: "chat",
  is_active: true,
  internal_default: false,
  enabled: true,
  description: null,
  created_at: "",
  updated_at: "",
} as Provider;

beforeEach(() => {
  vi.clearAllMocks();
  // Default: an active connection exists so the composer/draft surface renders.
  useProvidersMock.mockReturnValue({ data: [activeConnection] });
});

const agents: AgentInfo[] = [
  { agent_key: "claude_code", display_name: "Claude Code", available: true },
];

function renderDraft(overrides: Partial<React.ComponentProps<typeof DraftThread>> = {}) {
  const onSend = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DraftThread
          agents={agents}
          agentKey="claude_code"
          onAgentChange={vi.fn()}
          onSend={onSend}
          {...overrides}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { onSend };
}

describe("DraftThread", () => {
  test("shows the start guide and a composer right away (no working directory needed)", () => {
    renderDraft();
    expect(screen.getByText(/start a new conversation/i)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /message input/i })).toBeInTheDocument();
  });

  test("sends the typed first message through onSend", () => {
    const { onSend } = renderDraft();
    const box = screen.getByRole("textbox", { name: /message input/i });
    fireEvent.change(box, { target: { value: "first message" } });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: false });
    expect(onSend).toHaveBeenCalledWith("first message");
  });

  test("shows the no-managed-agent empty state when none is available", () => {
    renderDraft({ noManagedAgent: true });
    expect(screen.getByText("No managed agent available")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /message input/i })).not.toBeInTheDocument();
  });

  test("offers a model picker beside the agent selector and commits the choice", () => {
    const onModelChange = vi.fn();
    renderDraft({ onModelChange });
    // The active connection's model is listed in the dropdown — pick it.
    const trigger = screen.getByRole("combobox", { name: /agent model/i });
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    fireEvent.click(screen.getByRole("option", { name: "claude-opus-4-8" }));
    expect(onModelChange).toHaveBeenCalledWith("claude-opus-4-8");
  });

  acceptance("008-agent-chat", "chat runs on the built-in model when no connection", () => {
    // A Coffer LLM connection is an OPTIONAL override: with none configured the
    // agent runs on its own built-in login (chat shells out to its SDK/CLI), so
    // the draft must NOT block — the composer is available and there is no
    // "no connection" empty state (ADR-032 amendment D1).
    useProvidersMock.mockReturnValue({ data: [] });
    renderDraft();
    expect(screen.getByText(/start a new conversation/i)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /message input/i })).toBeInTheDocument();
    expect(screen.queryByText("No connection configured")).not.toBeInTheDocument();
  });

  test("no longer renders a working-directory input or folder picker", () => {
    // The per-turn working-directory UI was removed; turns default to the
    // Coffer-managed workspace on the backend.
    renderDraft();
    expect(screen.queryByRole("textbox", { name: /working directory/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /browse/i })).not.toBeInTheDocument();
  });
});
