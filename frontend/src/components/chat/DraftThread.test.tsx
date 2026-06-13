import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { DraftThread } from "./DraftThread";
import type { AgentInfo } from "@/lib/api/chat";
import type { Model } from "@/lib/api/models";

const agents: AgentInfo[] = [
  { agent_key: "builtin", display_name: "Coffer Assistant", available: true },
];
const models: Model[] = [
  {
    id: "m1",
    display_name: "Test Model",
    provider: "anthropic",
    model: "x",
    is_default: true,
    created_at: "x",
    updated_at: "x",
  },
];

function renderDraft(overrides: Partial<React.ComponentProps<typeof DraftThread>> = {}) {
  const onSend = vi.fn();
  const onCwdChange = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DraftThread
          agents={agents}
          models={models}
          agentKey="builtin"
          modelId="m1"
          cwd=""
          onAgentChange={vi.fn()}
          onModelChange={vi.fn()}
          onCwdChange={onCwdChange}
          onSend={onSend}
          {...overrides}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { onSend, onCwdChange };
}

const cliAgents: AgentInfo[] = [
  { agent_key: "builtin", display_name: "Coffer Assistant", available: true },
  { agent_key: "claude_code", display_name: "Claude Code", available: true },
];

describe("DraftThread", () => {
  test("shows the start guide and a composer when a model exists", () => {
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

  test("shows the no-model empty state instead of a composer when no models", () => {
    renderDraft({ models: [] });
    expect(screen.getByText("No model configured")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /message input/i })).not.toBeInTheDocument();
  });

  test("a CLI agent shows a working-directory input and no composer until cwd is set", () => {
    const { onCwdChange } = renderDraft({ agents: cliAgents, agentKey: "claude_code", cwd: "" });
    const dir = screen.getByRole("textbox", { name: /working directory/i });
    expect(dir).toBeInTheDocument();
    // No composer until a directory is provided.
    expect(screen.queryByRole("textbox", { name: /message input/i })).not.toBeInTheDocument();
    fireEvent.change(dir, { target: { value: "/home/me/project" } });
    expect(onCwdChange).toHaveBeenCalledWith("/home/me/project");
  });

  test("a CLI agent with a cwd shows the composer", () => {
    renderDraft({ agents: cliAgents, agentKey: "claude_code", cwd: "/home/me/project" });
    expect(screen.getByRole("textbox", { name: /message input/i })).toBeInTheDocument();
  });

  test("a CLI agent offers a folder Browse button next to the path field", () => {
    renderDraft({ agents: cliAgents, agentKey: "claude_code", cwd: "" });
    expect(screen.getByRole("button", { name: /browse/i })).toBeInTheDocument();
  });

  test("recent directories are offered and picking one sets the cwd", () => {
    const { onCwdChange } = renderDraft({
      agents: cliAgents,
      agentKey: "claude_code",
      cwd: "",
      recentCwds: ["/home/me/alpha", "/home/me/beta"],
    });
    // Open the recents popover and pick one.
    fireEvent.click(screen.getByRole("button", { name: /recent directories/i }));
    fireEvent.click(screen.getByText("/home/me/beta"));
    expect(onCwdChange).toHaveBeenCalledWith("/home/me/beta");
  });

  test("no recents control when there is no history", () => {
    renderDraft({ agents: cliAgents, agentKey: "claude_code", cwd: "", recentCwds: [] });
    expect(screen.queryByRole("button", { name: /recent directories/i })).not.toBeInTheDocument();
  });
});
