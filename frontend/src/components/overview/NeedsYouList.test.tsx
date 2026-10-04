// src/components/overview/NeedsYouList.test.tsx — a row's action that runs in place shows it is in progress.
//
// Real QueryClientProvider and router; the attention read, the MCP test call and
// the agent list are mocked.
import { afterEach, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import type { AttentionItem } from "@/lib/hooks/useAttention";
import { acceptance } from "@/test/acceptance";
import { NeedsYouList } from "./NeedsYouList";

vi.mock("@/lib/api/attention", () => ({ attentionApi: { read: vi.fn(), ignore: vi.fn() } }));
vi.mock("@/lib/api/mcpServers", () => ({ mcpServersApi: { test: vi.fn() } }));
vi.mock("@/lib/api/agentProviders", () => ({ agentProvidersApi: { list: vi.fn() } }));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: () => ({ data: [] }) }));
const { attentionApi } = await import("@/lib/api/attention");
const { mcpServersApi } = await import("@/lib/api/mcpServers");
const { agentProvidersApi } = await import("@/lib/api/agentProviders");

const server: AttentionItem = {
  key: "mcp_server:u1:mcp_start_failed",
  kind: "mcp_server",
  uid: "u1",
  title: "postgres",
  reason_code: "mcp_start_failed",
  reason: "Can't start: uvx isn't found on this machine.",
  severity: "error",
  since: null,
  action: {
    verb: "test",
    method: "POST",
    path: "/api/v1/resources/mcp_server/u1/test",
    body: null,
  },
  handoff: { prompt: "p" },
};
const agent: AttentionItem = {
  key: "agent:a1:agent_not_connected",
  kind: "agent",
  uid: "a1",
  title: "Claude Code",
  reason_code: "agent_not_connected",
  reason: "Not connected to Coffer.",
  severity: "warning",
  since: null,
  action: {
    verb: "connect",
    method: "POST",
    path: "/api/v1/agents/a1/coffer-connection",
    body: null,
  },
  handoff: { prompt: "p" },
};

afterEach(() => vi.clearAllMocks());

acceptance("web-ui", "a row's action that runs in place shows it is in progress", async () => {
  vi.mocked(agentProvidersApi.list).mockResolvedValue({ agents: [] });
  vi.mocked(attentionApi.read).mockResolvedValue({
    items: [server, agent],
    errors: [],
  } as never);
  let finish: () => void = () => {};
  vi.mocked(mcpServersApi.test).mockReturnValue(
    new Promise((resolve) => {
      finish = () => resolve({} as never);
    }),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <NeedsYouList />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Test again: postgres" }));
  const pending = await screen.findByRole("button", { name: "Retrying…: postgres" });
  expect(pending).toBeDisabled();
  expect(
    screen.getByText("Starting postgres… it leaves this list once it answers."),
  ).toBeInTheDocument();
  expect(mcpServersApi.test).toHaveBeenCalledWith("u1");
  expect(screen.getByRole("link", { name: "Connect: Claude Code" })).toBeInTheDocument();

  finish();
  // The list is read again after the call; the server is still listed, so the row reverts.
  expect(await screen.findByRole("button", { name: "Test again: postgres" })).toBeEnabled();
  await waitFor(() => expect(attentionApi.read).toHaveBeenCalledTimes(2));
  expect(screen.queryByText(/it leaves this list/)).not.toBeInTheDocument();
});
