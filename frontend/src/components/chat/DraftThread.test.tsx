import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { acceptance } from "@/test/acceptance";
import { DraftThread } from "./DraftThread";
import type { AgentProviderInfo } from "@/lib/api/agentProviders";
import type { Provider } from "@/lib/api/providers";

// The model picker (and the no-connection empty state) read the providers list.
vi.mock("@/lib/hooks/useProviders", () => ({ useProviders: vi.fn() }));
// The model picker reads the daemon's answer: with a
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

const MODELS: AgentModel[] = [
  {
    id: "opus",
    label: "Opus 5",
    description: "",
  },
];

const activeConnection = {
  name: "official",
  protocol: "anthropic",
  base_url: "https://api.anthropic.com",
  secret_ref: "ref",
  compatible_agents: ["claude_code"],
  transcribe_default: false,
  enabled: true,
  description: null,
  created_at: "",
  updated_at: "",
} as Provider;

beforeEach(() => {
  vi.clearAllMocks();
  // Default: an active connection exists so the composer/draft surface renders.
  useProvidersMock.mockReturnValue({ data: [activeConnection] });
  useAgentModelsMock.mockReturnValue({ data: MODELS });
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
    expect(screen.getByText(/New conversation with Claude Code in/)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /message input/i })).toBeInTheDocument();
    // The draft's title is in the title bar.
    expect(screen.getByRole("heading", { name: "New conversation" })).toBeInTheDocument();
  });

  test("says which agent runs in which folder, the folder in mono", () => {
    renderDraft({ cwd: "/Users/me/WorkEnv/AI/Coffer" });
    const line = screen.getByText(/New conversation with Claude Code in/);
    expect(line).toHaveTextContent(
      "New conversation with Claude Code in ~/WorkEnv/AI/Coffer — send a message to start.",
    );
    expect(within(line).getByText("~/WorkEnv/AI/Coffer")).toHaveClass("font-mono");
  });

  test("with no folder chosen the line names Coffer's workspace", () => {
    renderDraft();
    expect(screen.getByText(/New conversation with Claude Code in/)).toHaveTextContent(
      "in Coffer’s workspace — send a message",
    );
  });

  test("the folder picker sits in the composer toolbar, beside the paperclip", () => {
    renderDraft();
    const toolbar = screen.getByTestId("composer");
    expect(within(toolbar).getByRole("button", { name: "Workspace" })).toBeInTheDocument();
    expect(within(toolbar).getByRole("button", { name: "Attach files" })).toBeInTheDocument();
  });

  test("a draft opened from Ask an agent says nothing is sent until Send", () => {
    renderDraft({ fromHandoff: true });
    expect(screen.getByText("Nothing is sent until you press Send.")).toBeInTheDocument();
  });

  test("a plain draft carries no such line", () => {
    renderDraft();
    expect(screen.queryByText("Nothing is sent until you press Send.")).not.toBeInTheDocument();
  });

  test("sends the typed first message through onSend", () => {
    const { onSend } = renderDraft();
    const box = screen.getByRole("textbox", { name: /message input/i });
    fireEvent.change(box, { target: { value: "first message" } });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: false });
    expect(onSend).toHaveBeenCalledWith("first message", []);
  });

  acceptance("chat", "with no managed agent the draft links to the Agents page", () => {
    renderDraft({ noManagedAgent: true });
    expect(screen.getByRole("heading", { name: "New conversation" })).toBeInTheDocument();
    expect(screen.getByText("No agent connected")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Conversations run on an agent Coffer manages. Connect Claude Code or Codex on the Agents page first.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /message input/i })).not.toBeInTheDocument();
    // Connecting an agent is the Agents page's job: no install prompt to copy here.
    expect(screen.getByRole("link", { name: "Open Agents" })).toHaveAttribute("href", "/agents");
    expect(screen.queryByRole("button", { name: "Copy prompt" })).not.toBeInTheDocument();
  });

  test("only agents that can run are offered in the picker", () => {
    renderDraft({
      agents: [
        { agent_key: "claude_code", display_name: "Claude Code", available: true },
        { agent_key: "codex", display_name: "Codex", available: false },
      ],
    });
    fireEvent.keyDown(screen.getByRole("combobox", { name: /agent$/i }), { key: "ArrowDown" });
    expect(screen.getByRole("option", { name: "Claude Code" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /codex/i })).not.toBeInTheDocument();
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
    // "no connection" empty state (spec provider-switching "Revert an agent type
    // to its built-in login").
    useProvidersMock.mockReturnValue({ data: [] });
    renderDraft();
    expect(screen.getByText(/New conversation with Claude Code in/)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /message input/i })).toBeInTheDocument();
    expect(screen.queryByText("No connection configured")).not.toBeInTheDocument();
  });

  test("names the folder the turn will run in — Coffer's workspace when none was chosen", () => {
    renderDraft();
    expect(screen.getByRole("button", { name: "Workspace" })).toHaveTextContent(
      "Coffer’s workspace",
    );
  });

  test("the workspace is a picker: Coffer's workspace, recent folders, a typed path", () => {
    localStorage.setItem(
      "coffer.conversations.recentWorkingDirs",
      JSON.stringify(["/Users/me/a", "/Users/me/b"]),
    );
    const onCwdChange = vi.fn();
    renderDraft({ cwd: "/Users/me/a", onCwdChange });
    fireEvent.click(screen.getByRole("button", { name: "Workspace" }));

    const list = screen.getByRole("list", { name: "Workspace" });
    expect(
      within(list)
        .getAllByRole("button")
        .map((b) => b.textContent),
    ).toEqual(["Coffer’s workspace", "~/a", "~/b"]);
    expect(screen.getByRole("button", { name: "Choose…" })).toBeInTheDocument();

    fireEvent.click(within(list).getByRole("button", { name: "~/b" }));
    expect(onCwdChange).toHaveBeenLastCalledWith("/Users/me/b");
  });

  test("Coffer's workspace and a typed path can be chosen", () => {
    const onCwdChange = vi.fn();
    renderDraft({ cwd: "/Users/me/a", onCwdChange });
    fireEvent.click(screen.getByRole("button", { name: "Workspace" }));
    fireEvent.click(screen.getByRole("button", { name: "Coffer’s workspace" }));
    expect(onCwdChange).toHaveBeenLastCalledWith(null);

    fireEvent.click(screen.getByRole("button", { name: "Workspace" }));
    // One button: Choose… while the field is empty, Use once it holds a path.
    expect(screen.queryByRole("button", { name: "Use" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Type or paste a folder path" }), {
      target: { value: "  /srv/project " },
    });
    expect(screen.queryByRole("button", { name: "Choose…" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Use" }));
    expect(onCwdChange).toHaveBeenLastCalledWith("/srv/project");
  });

  test("an agent that cannot run is not offered", () => {
    renderDraft({
      agents: [
        { agent_key: "claude_code", display_name: "Claude Code", available: true },
        { agent_key: "codex", display_name: "Codex", available: false },
      ],
    });
    fireEvent.keyDown(screen.getByRole("combobox", { name: "Agent" }), { key: "ArrowDown" });
    expect(screen.queryByRole("option", { name: "Codex" })).not.toBeInTheDocument();
  });
});
