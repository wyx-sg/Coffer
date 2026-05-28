// frontend/src/kinds/mcp/McpServerDetailPage.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { McpServerDetailPage } from "./McpServerDetailPage";

vi.mock("@/lib/api/client", () => ({
  getApiClient: vi.fn(),
}));

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

const stdioResource = {
  ref: "mcp_server:fs",
  kind: "mcp_server",
  name: "fs",
  description: "Filesystem MCP",
  config: { transport: { type: "stdio", command: "npx" } },
  enabled: true,
  created_at: "2026-05-21T00:00:00Z",
  updated_at: "2026-05-21T00:00:00Z",
};

function wrap(ui: React.ReactNode, route = "/resources/mcp_server/fs") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/resources/mcp_server/:name" element={ui} />
          <Route path="/resources" element={<div data-testid="resources-page">resources</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("McpServerDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("renders resource name, description, and config JSON", async () => {
    const getMock = vi.fn().mockResolvedValue({
      data: stdioResource,
      error: undefined,
    });
    getApiClientMock.mockReturnValue({
      GET: getMock,
      POST: vi.fn(),
      DELETE: vi.fn(),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<McpServerDetailPage />));
    await waitFor(() => {
      expect(screen.getByText("fs")).toBeInTheDocument();
    });
    expect(screen.getByText("Filesystem MCP")).toBeInTheDocument();
    // The Overview tab shows the full config as a JSON block.
    expect(screen.getByText(/"command": "npx"/)).toBeInTheDocument();
  });

  test("enable switch fires disable mutation when enabled", async () => {
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    const getMock = vi.fn().mockResolvedValue({
      data: stdioResource,
      error: undefined,
    });
    getApiClientMock.mockReturnValue({
      GET: getMock,
      POST: postMock,
      DELETE: vi.fn(),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<McpServerDetailPage />));
    await waitFor(() => {
      expect(screen.getByText("fs")).toBeInTheDocument();
    });

    // Resource is enabled=true; aria-label reflects current state ("Enabled").
    // Click it to disable.
    const toggle = screen.getByRole("switch", { name: /^enabled$/i });
    fireEvent.click(toggle);

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith(
        "/resources/{kind}/{name}/disable",
        expect.objectContaining({
          params: { path: { kind: "mcp_server", name: "fs" } },
        }),
      );
    });
  });

  test("test connection button calls test endpoint and shows result", async () => {
    const getMock = vi.fn().mockResolvedValue({
      data: stdioResource,
      error: undefined,
    });
    const postMock = vi.fn().mockImplementation((path: string) => {
      if (path === "/resources/mcp_server/{name}/test") {
        return Promise.resolve({
          data: { ok: true, latency_ms: 42 },
          error: undefined,
        });
      }
      return Promise.resolve({ data: {}, error: undefined });
    });
    getApiClientMock.mockReturnValue({
      GET: getMock,
      POST: postMock,
      DELETE: vi.fn(),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<McpServerDetailPage />));
    await waitFor(() => {
      expect(screen.getByText("fs")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /test connection/i }));

    // A successful test surfaces the latency on the health badge.
    await waitFor(() => {
      expect(screen.getByTestId("health-badge")).toHaveTextContent(/42 ms/);
    });
  });

  test("health badge uses /status endpoint, not /capabilities — shows healthy even when capabilities fetch errors", async () => {
    // Regression test: list card and detail page must agree on health state.
    // The detail page used to derive healthState from the /capabilities fetch,
    // which (a) is slow and (b) conflates "discovery errored" with "failing".
    // After the fix, the header badge reads from /status (same source as the card).
    const getMock = vi.fn().mockImplementation((path: string) => {
      if (path === "/resources/mcp_server/{name}/status") {
        return Promise.resolve({ data: { status: "healthy" }, error: undefined });
      }
      if (path === "/resources/mcp_server/{name}/capabilities") {
        // Simulate a live-discovery failure — must NOT flip the badge to failing.
        return Promise.resolve({
          data: undefined,
          error: { error: { code: "UPSTREAM_UNAVAILABLE", message: "subprocess exited" } },
        });
      }
      // Default: return the resource (e.g. /resources/{kind}/{name})
      return Promise.resolve({ data: stdioResource, error: undefined });
    });
    getApiClientMock.mockReturnValue({
      GET: getMock,
      POST: vi.fn(),
      DELETE: vi.fn(),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<McpServerDetailPage />));

    // Wait for the page to load.
    await waitFor(() => {
      expect(screen.getByText("fs")).toBeInTheDocument();
    });

    // The badge must show "healthy" (from /status), not "failing" (from capsError).
    const badge = await screen.findByTestId("health-badge");
    expect(badge).toHaveTextContent("healthy");
    expect(badge).not.toHaveTextContent("failing");

    // The badge must also not be stuck on "unknown" while capabilities load.
    expect(badge).not.toHaveTextContent("unknown");
  });

  test("renders an error card when the resource fetch fails", async () => {
    const getMock = vi.fn().mockResolvedValue({
      data: undefined,
      error: { error: { code: "RESOURCE_NOT_FOUND", message: "no such server" } },
    });
    getApiClientMock.mockReturnValue({
      GET: getMock,
      POST: vi.fn(),
      DELETE: vi.fn(),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<McpServerDetailPage />));
    // The error branch renders a destructive card with the server's
    // error message + a "back to resources" link.
    expect(await screen.findByText(/no such server/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /back to resources/i })).toBeInTheDocument();
  });

  test("clicking Refresh invalidates the capabilities query", async () => {
    const getMock = vi.fn().mockImplementation((path: string) => {
      if (path === "/resources/mcp_server/{name}/capabilities") {
        return Promise.resolve({
          data: { tools: [], resources: [], prompts: [] },
          error: undefined,
        });
      }
      return Promise.resolve({ data: stdioResource, error: undefined });
    });
    getApiClientMock.mockReturnValue({
      GET: getMock,
      POST: vi.fn().mockResolvedValue({ data: {}, error: undefined }),
      DELETE: vi.fn(),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<McpServerDetailPage />));
    await waitFor(() => {
      expect(screen.getByText("fs")).toBeInTheDocument();
    });

    // Switch to the Tools tab so the capability list (and the Refresh
    // button) mounts. Once clicked, the capabilities query is invalidated
    // and re-fetched — assert by waiting for a second call to /capabilities.
    fireEvent.click(screen.getByRole("tab", { name: /tools/i }));
    const refreshBtn = await screen.findByRole("button", { name: /refresh/i });
    const initialCallCount = getMock.mock.calls.filter(
      ([path]) => path === "/resources/mcp_server/{name}/capabilities",
    ).length;
    fireEvent.click(refreshBtn);
    await waitFor(() => {
      const after = getMock.mock.calls.filter(
        ([path]) => path === "/resources/mcp_server/{name}/capabilities",
      ).length;
      expect(after).toBeGreaterThan(initialCallCount);
    });
  });

  test("test connection failure surfaces the error banner", async () => {
    const getMock = vi.fn().mockResolvedValue({
      data: stdioResource,
      error: undefined,
    });
    const postMock = vi.fn().mockImplementation((path: string) => {
      if (path === "/resources/mcp_server/{name}/test") {
        return Promise.resolve({
          data: undefined,
          error: { error: { code: "UPSTREAM_UNAVAILABLE", message: "connection refused" } },
        });
      }
      return Promise.resolve({ data: {}, error: undefined });
    });
    getApiClientMock.mockReturnValue({
      GET: getMock,
      POST: postMock,
      DELETE: vi.fn(),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<McpServerDetailPage />));
    await waitFor(() => {
      expect(screen.getByText("fs")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /test connection/i }));
    // The failure path sets testResult to {ok: false, ...} and renders
    // the destructive "test failure" inline banner with the error message.
    expect(await screen.findByText(/connection refused/i)).toBeInTheDocument();
  });

  test("delete dialog requires confirmation before deleting", async () => {
    const getMock = vi.fn().mockResolvedValue({
      data: stdioResource,
      error: undefined,
    });
    const deleteMock = vi.fn().mockResolvedValue({ data: undefined, error: undefined });
    getApiClientMock.mockReturnValue({
      GET: getMock,
      POST: vi.fn(),
      DELETE: deleteMock,
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<McpServerDetailPage />));
    await waitFor(() => {
      expect(screen.getByText("fs")).toBeInTheDocument();
    });

    // Open delete dialog
    fireEvent.click(screen.getByRole("button", { name: /delete server/i }));
    await screen.findByText(/delete mcp_server:fs/i);

    // Confirm deletion
    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));

    await waitFor(() => {
      expect(deleteMock).toHaveBeenCalledWith(
        "/resources/{kind}/{name}",
        expect.objectContaining({
          params: { path: { kind: "mcp_server", name: "fs" } },
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId("resources-page")).toBeInTheDocument();
    });
  });
});
