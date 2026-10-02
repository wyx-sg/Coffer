// src/components/handoff/AgentHandoff.test.tsx — Copy prompt, and Ask an agent opening the draft.
//
// Real QueryClientProvider; only the agent-providers api is mocked.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { readHandoffState } from "@/lib/conversations/handoff";
import { AgentHandoff } from "./AgentHandoff";

vi.mock("@/lib/api/agentProviders", () => ({ agentProvidersApi: { list: vi.fn() } }));
const { agentProvidersApi } = await import("@/lib/api/agentProviders");
const listAgents = vi.mocked(agentProvidersApi.list);

const PROMPT = "Install jq 1.6 or newer on this machine.";

function Draft() {
  const handoff = readHandoffState(useLocation().state);
  return <div data-testid="draft">{handoff ? `${handoff.agentKey}: ${handoff.prompt}` : ""}</div>;
}

function renderHandoff(available: boolean) {
  listAgents.mockResolvedValue({
    agents: [{ agent_key: "claude_code", display_name: "Claude Code", available }],
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/clis/jq"]}>
        <Routes>
          <Route path="/clis/:command" element={<AgentHandoff prompt={PROMPT} />} />
          <Route path="/conversations/new" element={<Draft />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const writeText = vi.fn().mockResolvedValue(undefined);
beforeEach(() => {
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
});
afterEach(() => vi.clearAllMocks());

describe("AgentHandoff", () => {
  test("Copy prompt copies the prompt as given", async () => {
    renderHandoff(true);
    fireEvent.click(screen.getByRole("button", { name: "Copy prompt" }));
    expect(writeText).toHaveBeenCalledWith(PROMPT);
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  test("Ask an agent opens the draft with the prompt, no dialog first", async () => {
    renderHandoff(true);
    fireEvent.click(await screen.findByRole("button", { name: "Ask an agent" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(await screen.findByTestId("draft")).toHaveTextContent(`claude_code: ${PROMPT}`);
  });

  test("with no managed agent available only Copy prompt is offered", async () => {
    renderHandoff(false);
    await waitFor(() => expect(listAgents).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByRole("button", { name: "Copy prompt" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask an agent" })).toBeNull();
  });
});
