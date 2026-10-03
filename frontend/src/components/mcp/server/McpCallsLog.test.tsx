// frontend/src/components/mcp/server/McpCallsLog.test.tsx
// A server's calls tab is the Activity calls table scoped to it (spec web-ui).
import { vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { McpCallsLog } from "./McpCallsLog";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ActivityPage } from "@/pages/activity/ActivityPage";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: vi.fn(),
}));
// Activity's MCP calls tab, mounted by the acceptance test below, follows the
// daemon's change feed; no stream is opened here.
vi.mock("@/lib/events/eventStream", () => ({
  followDaemonEvents: () => new Promise<void>(() => {}),
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: () => ({ data: [] }) }));

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchInterval: false as never },
      mutations: { retry: false },
    },
  });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

// Both rows belong to the same server. The uid is what the log records; the
// name is what a reader sees — deliberately not the same string, so a column
// that rendered the wrong one could not pass.
const sampleInvocations = [
  {
    id: 1,
    agent_uid: null,
    timestamp: new Date(Date.now() - 30_000).toISOString(), // 30 seconds ago
    resource_uid: "u-filesystem",
    resource_name: "fs",
    capability_type: "tool" as const,
    capability_key: "read_file",
    duration_ms: 42,
    status: "ok" as const,
    error_message: null,
    session_id: null,
  },
  {
    id: 2,
    agent_uid: null,
    timestamp: new Date(Date.now() - 90_000).toISOString(), // 90 seconds ago
    resource_uid: "u-filesystem",
    resource_name: "fs",
    capability_type: "resource" as const,
    capability_key: "file://foo.txt",
    duration_ms: 500,
    status: "error" as const,
    error_message: "connection refused",
    session_id: null,
  },
];

acceptance(
  "web-ui",
  "a server's invocations tab is the Activity calls table scoped to it",
  async () => {
    const get = vi.fn().mockResolvedValue({
      data: { invocations: sampleInvocations },
      error: undefined,
    });
    getApiClientMock.mockReturnValue({ GET: get } as unknown as ReturnType<typeof getApiClient>);

    // The server's Invocations tab: that server's calls, no server column; a
    // row opens its call in a drawer.
    const scoped = render(
      wrap(<McpCallsLog serverUid="u-filesystem" serverName="fs" transport="stdio" agents={[]} />),
    );
    await waitFor(() => expect(screen.getAllByText("read_file").length).toBeGreaterThan(0));
    expect(get.mock.calls.every((c) => c[1]?.params?.path?.uid === "u-filesystem")).toBe(true);
    expect(get.mock.calls[0][0]).toBe("/resources/mcp_server/{uid}/invocations");
    expect(screen.queryByRole("columnheader", { name: /server/i })).not.toBeInTheDocument();
    expect(screen.queryByTestId("mcp-call-drawer")).toBeNull();
    fireEvent.click(screen.getAllByText("read_file")[0]);
    const drawer = await screen.findByTestId("mcp-call-drawer");
    expect(drawer).toHaveTextContent("read_file");
    expect(drawer).toHaveTextContent("fs · stdio");
    expect(screen.getByRole("button", { name: "View server log" })).toBeInTheDocument();
    scoped.unmount();

    // Activity's MCP calls tab reads the same log unscoped: every server's
    // calls from the cross-server route, each row naming its server.
    get.mockClear();
    render(
      wrap(
        <TooltipProvider>
          <MemoryRouter initialEntries={["/activity?tab=mcp"]}>
            <ActivityPage />
          </MemoryRouter>
        </TooltipProvider>,
      ),
    );
    // Activity's MCP calls table mutes the server part of `server.tool` in its own span.
    const fsReadFile = (_: string, el: Element | null) =>
      el?.hasAttribute("data-call-target") === true && el.textContent === "fs.read_file";
    await waitFor(() => expect(screen.getAllByText(fsReadFile).length).toBeGreaterThan(0));
    const logReads = get.mock.calls.filter((c) => String(c[0]).includes("invocations"));
    expect(logReads.every((c) => c[0] === "/mcp/invocations")).toBe(true);
    expect(logReads.every((c) => c[1]?.params?.query?.uid === undefined)).toBe(true);
    expect(screen.getByRole("columnheader", { name: "Server · tool" })).toBeInTheDocument();
  },
);
