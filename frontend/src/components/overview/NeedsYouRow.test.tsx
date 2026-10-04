// src/components/overview/NeedsYouRow.test.tsx — every row offers the item's hand-off as a split button and a ⋯ menu with Ignore.
//
// Real QueryClientProvider and router; only the agent-providers api is mocked.
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { AttentionItem } from "@/lib/hooks/useAttention";
import { OPEN_APPROVALS_EVENT } from "@/lib/hooks/useApprovals";
import { acceptance } from "@/test/acceptance";
import { NeedsYouRow } from "./NeedsYouRow";

vi.mock("@/lib/api/agentProviders", () => ({ agentProvidersApi: { list: vi.fn() } }));
vi.mock("@/lib/api/fs", () => ({ fsApi: { listTerminals: vi.fn(), openTerminal: vi.fn() } }));
const { agentProvidersApi } = await import("@/lib/api/agentProviders");
const { fsApi } = await import("@/lib/api/fs");
const listAgents = vi.mocked(agentProvidersApi.list);
const openTerminal = vi.mocked(fsApi.openTerminal);

const PROMPT = "Please install `uvx` on this machine so MCP server fetch can start.";

function item(overrides: Partial<AttentionItem> = {}): AttentionItem {
  return {
    key: "mcp_server:u1:mcp_missing_launcher",
    kind: "mcp_server",
    uid: "u1",
    title: "fetch",
    reason_code: "mcp_missing_launcher",
    reason: "Its launcher uvx isn't found on this machine.",
    severity: "error",
    since: null,
    action: {
      verb: "test",
      method: "POST",
      path: "/api/v1/resources/mcp_server/u1/test",
      body: null,
    },
    handoff: { prompt: PROMPT },
    ...overrides,
  };
}

const onIgnore = vi.fn();

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
                <NeedsYouRow item={row} onIgnore={onIgnore} />
              </ul>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const writeText = vi.fn().mockResolvedValue(undefined);
beforeEach(() => {
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  vi.mocked(fsApi.listTerminals).mockResolvedValue([]);
  openTerminal.mockResolvedValue(undefined);
});
afterEach(() => vi.clearAllMocks());

function openMenu() {
  fireEvent.click(screen.getByRole("button", { name: "More for fetch" }));
}

acceptance("web-ui", "a needs-you row offers the item's hand-off in its menu", async () => {
  renderRow(item(), true);
  await waitFor(() => expect(listAgents).toHaveBeenCalled());
  fireEvent.click(await screen.findByRole("button", { name: "More options" }));
  fireEvent.click(await screen.findByRole("menuitem", { name: /^Copy prompt/ }));
  // Copying is asynchronous (it toasts "Prompt copied" afterwards).
  await waitFor(() => expect(writeText).toHaveBeenCalledWith(PROMPT));
  expect(openTerminal).not.toHaveBeenCalled();

  // The main part starts the hand-off agent in the preferred terminal with the prompt.
  fireEvent.click(screen.getByRole("button", { name: "Hand off to Claude Code" }));
  await waitFor(() =>
    expect(openTerminal).toHaveBeenCalledWith({
      agent: "claude_code",
      prompt: PROMPT,
      terminal: null,
    }),
  );
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("with no managed agent available the row offers a Copy prompt button only", async () => {
  renderRow(item(), false);
  await waitFor(() => expect(listAgents).toHaveBeenCalled());
  expect(await screen.findByRole("button", { name: /^Copy prompt/ })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Hand off to/ })).not.toBeInTheDocument();
});

test("every row's menu ends with Ignore", async () => {
  renderRow(item({ severity: "error" }), false);
  await waitFor(() => expect(listAgents).toHaveBeenCalled());
  openMenu();
  fireEvent.click(await screen.findByRole("menuitem", { name: "Ignore" }));
  expect(onIgnore).toHaveBeenCalledTimes(1);
});

acceptance("web-ui", "a needs-you row's action reads what it does for its kind", () => {
  const verbOf = (verb: string): AttentionItem["action"] => ({
    verb,
    method: "GET",
    path: "/api/v1/x",
    body: null,
  });
  renderRow(
    item({
      kind: "channel",
      title: "SeaTalk",
      reason_code: "channel_disconnected",
      action: verbOf("check"),
    }),
    false,
  );
  // A channel's check reads Reconnect channel, behind its verb's 14px icon.
  const reconnect = screen.getByRole("link", { name: "Reconnect channel: SeaTalk" });
  expect(reconnect.querySelector("svg")).not.toBeNull();
  cleanup();
  renderRow(
    item({
      kind: "sync",
      uid: null,
      title: "Vault sync",
      reason_code: "held",
      action: verbOf("review"),
    }),
    false,
  );
  expect(screen.getByRole("link", { name: "Review held changes: Vault sync" })).toBeInTheDocument();
});

test("Review on waiting approvals opens the global dialog instead of leaving Overview", async () => {
  const opened = vi.fn();
  window.addEventListener(OPEN_APPROVALS_EVENT, opened);
  renderRow(
    item({
      key: "secret:fp:secret_approvals_pending",
      kind: "secret",
      uid: "fp",
      title: "Secret approvals",
      reason_code: "secret_approvals_pending",
      reason: "2 changes waiting for approval.",
      severity: "warning",
      action: { verb: "review", method: "GET", path: "/api/v1/secrets/approvals", body: null },
    }),
    false,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Review: Secret approvals" }));
  expect(opened).toHaveBeenCalledTimes(1);
  // Still on Overview: no link was followed.
  window.removeEventListener(OPEN_APPROVALS_EVENT, opened);
});

test("a secret that has no value here is opened on the Secrets page", async () => {
  renderRow(
    item({
      key: "secret:fp:secret_missing_here",
      kind: "secret",
      uid: "fp",
      title: "Secrets",
      reason_code: "secret_missing_here",
      reason: "3 secrets have no value on this Mac.",
      action: { verb: "open", method: "GET", path: "/api/v1/secrets", body: null },
    }),
    false,
  );
  const open = await screen.findByRole("link", { name: "Open Secrets: Secrets" });
  expect(open).toHaveAttribute("href", "/secrets");
});
