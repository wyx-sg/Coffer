// src/components/handoff/AgentHandoff.test.tsx — Copy prompt, the only hand-off while the web chat is gone.
//
// Real QueryClientProvider; only the agent-providers api is mocked.
import { acceptance } from "@/test/acceptance";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { ToastProvider } from "@/components/ui/toast";
import { AgentHandoff } from "./AgentHandoff";

vi.mock("@/lib/api/agentProviders", () => ({ agentProvidersApi: { list: vi.fn() } }));
const { agentProvidersApi } = await import("@/lib/api/agentProviders");
const listAgents = vi.mocked(agentProvidersApi.list);

const PROMPT = "Install jq 1.6 or newer on this machine.";

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
    fireEvent.click(await screen.findByRole("button", { name: "Copy prompt" }));
    expect(writeText).toHaveBeenCalledWith(PROMPT);
    expect(await screen.findByText("Prompt copied")).toBeInTheDocument();
  });

  test("a prompt that is a request is made when Copy prompt is picked", async () => {
    const request = vi.fn(() => Promise.resolve("asked for"));
    renderHandoff(true, request);
    await waitFor(() => expect(listAgents).toHaveBeenCalled());
    expect(request).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole("button", { name: "Copy prompt" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("asked for"));
    expect(request).toHaveBeenCalledWith({ agent: null });
  });

  test("a button with autoSend still offers Copy prompt only", async () => {
    renderHandoff(true, PROMPT, { label: "Tidy" });
    fireEvent.click(await screen.findByRole("button", { name: "Copy prompt" }));
    expect(writeText).toHaveBeenCalledWith(PROMPT);
    expect(screen.queryByRole("button", { name: "Tidy" })).not.toBeInTheDocument();
  });

  test("Ask an agent and the options menu are not offered", async () => {
    renderHandoff(true);
    await waitFor(() => expect(listAgents).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByRole("button", { name: "Copy prompt" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask an agent" })).toBeNull();
    expect(screen.queryByRole("button", { name: "More options" })).toBeNull();
  });
});
