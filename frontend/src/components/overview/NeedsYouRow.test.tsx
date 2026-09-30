// src/components/overview/NeedsYouRow.test.tsx — a row whose item carries a hand-off offers it in its ⋯ menu.
//
// Real QueryClientProvider and router; only the agent-providers api is mocked.
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { readHandoffState } from "@/lib/conversations/handoff";
import type { AttentionItem } from "@/lib/hooks/useAttention";
import { acceptance } from "@/test/acceptance";
import { NeedsYouRow } from "./NeedsYouRow";

vi.mock("@/lib/api/agentProviders", () => ({ agentProvidersApi: { list: vi.fn() } }));
const { agentProvidersApi } = await import("@/lib/api/agentProviders");
const listAgents = vi.mocked(agentProvidersApi.list);

const PROMPT = "Please install `uvx` on this machine so MCP server fetch can start.";

function item(overrides: Partial<AttentionItem> = {}): AttentionItem {
  return {
    key: "mcp_server:u1:mcp_missing_launcher",
    ignorable: false,
    kind: "mcp_server",
    uid: "u1",
    title: "fetch",
    reason_code: "mcp_missing_launcher",
    reason: "Its launcher uvx isn't found on this machine.",
    severity: "error",
    since: null,
    action: { verb: "test", method: "POST", path: "/api/v1/resources/mcp_server/u1/test", body: null },
    handoff: { prompt: PROMPT },
    ...overrides,
  };
}

function Draft() {
  const handoff = readHandoffState(useLocation().state);
  return <div data-testid="draft">{handoff ? handoff.prompt : ""}</div>;
}

function renderRow(row: AttentionItem, available: boolean) {
  listAgents.mockResolvedValue({
    agents: [{ agent_key: "claude_code", display_name: "Claude Code", available }],
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route
            path="/"
            element={
              <ul>
                <NeedsYouRow item={row} />
              </ul>
            }
          />
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

function openMenu() {
  fireEvent.click(screen.getByRole("button", { name: "More for fetch" }));
}

acceptance("web-ui", "a needs-you row offers the item's hand-off in its menu", async () => {
  renderRow(item(), true);
  await waitFor(() => expect(listAgents).toHaveBeenCalled());
  openMenu();
  fireEvent.click(await screen.findByRole("menuitem", { name: "Copy prompt" }));
  expect(writeText).toHaveBeenCalledWith(PROMPT);

  openMenu();
  fireEvent.click(await screen.findByRole("menuitem", { name: "Ask an agent" }));
  const dialog = await screen.findByRole("dialog");
  const start = within(dialog).getByRole("button", { name: "Start" });
  await waitFor(() => expect(start).toBeEnabled());
  fireEvent.click(start);
  expect(await screen.findByTestId("draft")).toHaveTextContent(PROMPT);
});

test("with no managed agent available the menu offers Copy prompt only", async () => {
  renderRow(item(), false);
  await waitFor(() => expect(listAgents).toHaveBeenCalled());
  openMenu();
  expect(await screen.findByRole("menuitem", { name: "Copy prompt" })).toBeInTheDocument();
  expect(screen.queryByRole("menuitem", { name: "Ask an agent" })).not.toBeInTheDocument();
});

test("a row with no hand-off that cannot be ignored has no menu", () => {
  renderRow(item({ handoff: null }), true);
  expect(screen.queryByRole("button", { name: "More for fetch" })).not.toBeInTheDocument();
});
