import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { acceptance } from "@/test/acceptance";
import { DraftThread } from "./DraftThread";
import type { AgentProviderInfo } from "@/lib/api/agentProviders";
import type { Provider } from "@/lib/api/providers";

// The model picker (and the no-connection empty state) read the providers list.
vi.mock("@/lib/hooks/useProviders", () => ({ useProviders: vi.fn() }));
// The model AND effort pickers both read the daemon's answer now — with a
// connection active it is that connection's curated ids, resolved server-side.
// The picker used to introspect the endpoint from the browser and union the
// result with the agent's own catalogue; it no longer reaches the network at
// all, so there is no introspection hook to mock here.
vi.mock("@/lib/hooks/useAgentModels", () => ({ useAgentModels: vi.fn() }));

import { useProviders } from "@/lib/hooks/useProviders";
import { useAgentModels } from "@/lib/hooks/useAgentModels";
import type { AgentModel } from "@/lib/api/agentModels";
const useProvidersMock = useProviders as unknown as ReturnType<typeof vi.fn>;
const useAgentModelsMock = useAgentModels as unknown as ReturnType<typeof vi.fn>;

/** Claude Code's entries now carry the SDK's reasoning levels; an agent whose
 * models report none is what the self-hiding rule is checked against. */
const WITH_LEVELS: AgentModel[] = [
  {
    id: "opus",
    label: "Opus 5",
    description: "",
    efforts: ["low", "medium", "high", "xhigh", "max"],
    default_effort: null,
  },
];
const WITHOUT_LEVELS: AgentModel[] = [
  { id: "opus", label: "Opus 5", description: "", efforts: [], default_effort: null },
];

const activeConnection = {
  name: "official",
  protocol: "anthropic",
  base_url: "https://api.anthropic.com",
  credential_ref: "ref",
  compatible_agents: ["claude_code"],
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
  useAgentModelsMock.mockReturnValue({ data: WITH_LEVELS });
});

const agents: AgentProviderInfo[] = [
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
    // Whatever the daemon offered for this agent is what the dropdown lists.
    const trigger = screen.getByRole("combobox", { name: /agent model/i });
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    fireEvent.click(screen.getByRole("option", { name: /^Opus 5\s*opus$/ }));
    expect(onModelChange).toHaveBeenCalledWith("opus");
  });

  acceptance("chat", "chat runs on the built-in model when no connection", () => {
    // A Coffer LLM connection is an OPTIONAL override: with none configured the
    // agent runs on its own built-in login (chat shells out to its SDK/CLI), so
    // the draft must NOT block — the composer is available and there is no
    // "no connection" empty state (the provider-switching ADR, amendment D1).
    useProvidersMock.mockReturnValue({ data: [] });
    renderDraft();
    expect(screen.getByText(/start a new conversation/i)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /message input/i })).toBeInTheDocument();
    expect(screen.queryByText("No connection configured")).not.toBeInTheDocument();
  });

  test("offers an effort picker beside the model picker and commits the choice", () => {
    // The draft is where the FIRST turn's level is chosen; after the fact the
    // turn the user cared about is already running.
    const onEffortChange = vi.fn();
    renderDraft({ onEffortChange });

    const trigger = screen.getByRole("combobox", { name: /reasoning effort/i });
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    fireEvent.click(screen.getByRole("option", { name: "xhigh" }));

    expect(onEffortChange).toHaveBeenCalledWith("xhigh");
  });

  test("renders no effort control for an agent whose models report no levels", () => {
    // Same self-hiding rule as the open conversation's bar: nothing to choose
    // between means no control at all, not a disabled or empty one.
    useAgentModelsMock.mockReturnValue({ data: WITHOUT_LEVELS });
    renderDraft();

    expect(screen.queryByRole("combobox", { name: /reasoning effort/i })).not.toBeInTheDocument();
    // ...and the rest of the bar is untouched.
    expect(screen.getByRole("combobox", { name: /agent model/i })).toBeInTheDocument();
  });

  test("no longer renders a working-directory input or folder picker", () => {
    // The per-turn working-directory UI was removed; turns default to the
    // Coffer-managed workspace on the backend.
    renderDraft();
    expect(screen.queryByRole("textbox", { name: /working directory/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /browse/i })).not.toBeInTheDocument();
  });
});
