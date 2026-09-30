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
// With no managed agent the draft reads the daemon's install prompt, if any.
vi.mock("@/lib/hooks/useAgentTypes", () => ({ useAgentInstallHandoff: vi.fn() }));

import { useProviders } from "@/lib/hooks/useProviders";
import { useAgentModels } from "@/lib/hooks/useAgentModels";
import { useAgentInstallHandoff } from "@/lib/hooks/useAgentTypes";
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
  secret_ref: "ref",
  compatible_agents: ["claude_code"],
  is_active: true,
  internal_default: false,
  transcribe_default: false,
  fallback: true,
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
  vi.mocked(useAgentInstallHandoff).mockReturnValue({ data: null } as never);
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
  test("shows the draft's composer right away, with no welcome page", () => {
    renderDraft();
    expect(screen.getByText("New conversation with Claude Code")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /message input/i })).toBeInTheDocument();
  });

  test("says what the first turn runs with: folder, model and effort, when chosen", () => {
    renderDraft({ cwd: "/Users/me/WorkEnv/AI/Coffer", modelValue: "opus", effortValue: "high" });
    expect(
      screen.getByText("~/WorkEnv/AI/Coffer · Opus 5 · high effort — send a message to start."),
    ).toBeInTheDocument();
  });

  test("leaves out the model and effort that were not chosen", () => {
    renderDraft();
    expect(screen.getByText("Coffer’s workspace — send a message to start.")).toBeInTheDocument();
  });

  test("sends the typed first message through onSend", () => {
    const { onSend } = renderDraft();
    const box = screen.getByRole("textbox", { name: /message input/i });
    fireEvent.change(box, { target: { value: "first message" } });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: false });
    expect(onSend).toHaveBeenCalledWith("first message", []);
  });

  test("shows the no-managed-agent empty state when none is available", () => {
    renderDraft({ noManagedAgent: true });
    expect(screen.getByText("No managed agent available")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /message input/i })).not.toBeInTheDocument();
    // An agent is installed but not added: adding it is Coffer's own action.
    expect(screen.getByRole("link", { name: "Open Agents" })).toHaveAttribute("href", "/agents");
    expect(screen.queryByRole("button", { name: "Copy prompt" })).not.toBeInTheDocument();
  });

  acceptance(
    "chat",
    "with no managed agent the draft offers the install prompt to copy",
    async () => {
      vi.mocked(useAgentInstallHandoff).mockReturnValue({
        data: "Please install Claude Code or OpenAI Codex on this machine.",
      } as never);
      const writeText = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, { clipboard: { writeText } });
      renderDraft({ noManagedAgent: true });
      fireEvent.click(screen.getByRole("button", { name: "Copy prompt" }));
      expect(writeText).toHaveBeenCalledWith(
        "Please install Claude Code or OpenAI Codex on this machine.",
      );
      // Copy only: there is no agent of Coffer's to ask, and no install command.
      expect(screen.queryByRole("button", { name: "Ask an agent" })).not.toBeInTheDocument();
      expect(document.body).not.toHaveTextContent(/npm|install -g|brew/);
    },
  );

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
    // "no connection" empty state (spec provider-switching "Revert an agent type
    // to its built-in login").
    useProvidersMock.mockReturnValue({ data: [] });
    renderDraft();
    expect(screen.getByText("New conversation with Claude Code")).toBeInTheDocument();
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

  test("names the folder the turn will run in — Coffer's workspace when none was chosen", () => {
    // The folder is chosen in New conversation; the draft only shows it.
    renderDraft();
    expect(screen.getByText("Coffer’s workspace")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /working directory/i })).not.toBeInTheDocument();
  });
});
