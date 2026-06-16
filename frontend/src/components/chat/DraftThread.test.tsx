import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { DraftThread } from "./DraftThread";
import type { AgentInfo } from "@/lib/api/chat";

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

  test("no longer renders a working-directory input or folder picker", () => {
    // The per-turn working-directory UI was removed; turns default to the
    // Coffer-managed workspace on the backend.
    renderDraft();
    expect(
      screen.queryByRole("textbox", { name: /working directory/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /browse/i })).not.toBeInTheDocument();
  });
});
