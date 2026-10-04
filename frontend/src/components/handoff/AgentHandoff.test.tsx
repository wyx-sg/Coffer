// src/components/handoff/AgentHandoff.test.tsx — Copy prompt, and Ask an agent opening the draft.
//
// Real QueryClientProvider; only the agent-providers api is mocked.
import { acceptance } from "@/test/acceptance";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { readHandoffState } from "@/lib/conversations/handoff";
import { ToastProvider } from "@/components/ui/toast";
import { AgentHandoff } from "./AgentHandoff";

vi.mock("@/lib/api/agentProviders", () => ({ agentProvidersApi: { list: vi.fn() } }));
const { agentProvidersApi } = await import("@/lib/api/agentProviders");
const listAgents = vi.mocked(agentProvidersApi.list);

const PROMPT = "Install jq 1.6 or newer on this machine.";

function Draft() {
  const handoff = readHandoffState(useLocation().state);
  return (
    <div data-testid="draft">
      {handoff ? `${handoff.agentKey}: ${handoff.prompt}${handoff.autoSend ? " (sent)" : ""}` : ""}
    </div>
  );
}

function renderHandoff(
  available: boolean,
  prompt: React.ComponentProps<typeof AgentHandoff>["prompt"] = PROMPT,
  autoSend?: { label: string },
) {
  listAgents.mockResolvedValue({
    agents: [{ agent_key: "claude_code", display_name: "Claude Code", available }],
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={["/clis/jq"]}>
          <Routes>
            <Route
              path="/clis/:command"
              element={<AgentHandoff prompt={prompt} autoSend={autoSend} />}
            />
            <Route path="/conversations/new" element={<Draft />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const writeText = vi.fn().mockResolvedValue(undefined);
beforeEach(() => {
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
});
afterEach(() => vi.clearAllMocks());

describe("AgentHandoff", () => {
  acceptance("web-ui", "the split button hands a prompt over or copies it", async () => {
    renderHandoff(true);
    await screen.findByRole("button", { name: "Ask an agent" });
    fireEvent.click(screen.getByRole("button", { name: "More options" }));
    expect(screen.getByText("For an agent outside Coffer")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("menuitem", { name: /Copy prompt/ }));
    expect(writeText).toHaveBeenCalledWith(PROMPT);
    expect(await screen.findByText("Prompt copied")).toBeInTheDocument();
  });

  test("a prompt that is a request is made when Ask an agent is picked, naming the agent", async () => {
    const request = vi.fn(() => Promise.resolve("asked for"));
    renderHandoff(true, request);
    await screen.findByRole("button", { name: "Ask an agent" });
    expect(request).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Ask an agent" }));
    expect(await screen.findByTestId("draft")).toHaveTextContent("claude_code: asked for");
    expect(request).toHaveBeenCalledWith({ agent: "Claude Code" });
  });

  test("a button with autoSend carries its label and asks for the prompt to be sent", async () => {
    renderHandoff(true, PROMPT, { label: "Tidy" });
    fireEvent.click(await screen.findByRole("button", { name: "Tidy" }));
    expect(await screen.findByTestId("draft")).toHaveTextContent(`claude_code: ${PROMPT} (sent)`);
  });

  test("an autoSend button with no managed agent offers Copy prompt only", async () => {
    renderHandoff(false, PROMPT, { label: "Tidy" });
    fireEvent.click(await screen.findByRole("button", { name: "Copy prompt" }));
    expect(writeText).toHaveBeenCalledWith(PROMPT);
    expect(screen.queryByRole("button", { name: "Tidy" })).not.toBeInTheDocument();
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
    expect(screen.queryByRole("button", { name: "More options" })).toBeNull();
  });
});
