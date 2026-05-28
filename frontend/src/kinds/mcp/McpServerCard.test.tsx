// frontend/src/kinds/mcp/McpServerCard.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { McpServerCard } from "./McpServerCard";
import type { components } from "@/lib/api/types";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

type ResourceOut = components["schemas"]["ResourceOut"];

/** Mock the API; `status` seeds the per-server status endpoint. */
function mockApi(status: "healthy" | "failing" | "unknown" = "unknown") {
  getApiClientMock.mockReturnValue({
    GET: vi.fn().mockResolvedValue({ data: { status }, error: undefined }),
    POST: vi.fn().mockResolvedValue({ data: {}, error: undefined }),
    DELETE: vi.fn().mockResolvedValue({ data: undefined, error: undefined }),
  } as unknown as ReturnType<typeof getApiClient>);
}

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function renderRouted(resource: ResourceOut) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/resources"]}>
        <Routes>
          <Route path="/resources" element={<McpServerCard resource={resource} />} />
          <Route
            path="/resources/mcp_server/:name"
            element={<div data-testid="detail-page">detail</div>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const stdioServer: ResourceOut = {
  ref: "mcp_server:fs",
  kind: "mcp_server",
  name: "fs",
  description: "Filesystem MCP",
  config: { transport: { type: "stdio", command: "npx" } },
  enabled: true,
  created_at: "2026-05-21T00:00:00Z",
  updated_at: "2026-05-21T00:00:00Z",
};

describe("McpServerCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi();
  });

  test("shows the server name + transport + enabled badge", () => {
    render(wrap(<McpServerCard resource={stdioServer} />));
    expect(screen.getAllByText("fs").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("stdio")).toBeInTheDocument();
    expect(screen.getByText("enabled")).toBeInTheDocument();
    expect(screen.getByText("Filesystem MCP")).toBeInTheDocument();
  });

  test("clicking anywhere on the card navigates to the detail page", () => {
    renderRouted(stdioServer);
    fireEvent.click(screen.getByText("stdio"));
    expect(screen.getByTestId("detail-page")).toBeInTheDocument();
  });

  test("the card is keyboard-navigable (Enter opens the detail page)", () => {
    renderRouted(stdioServer);
    fireEvent.keyDown(screen.getByRole("link"), { key: "Enter" });
    expect(screen.getByTestId("detail-page")).toBeInTheDocument();
  });

  test("renders 'disabled' state when enabled=false", () => {
    render(wrap(<McpServerCard resource={{ ...stdioServer, enabled: false }} />));
    expect(screen.getByText("disabled")).toBeInTheDocument();
  });

  test("handles missing config gracefully", () => {
    render(wrap(<McpServerCard resource={{ ...stdioServer, config: {} }} />));
    expect(screen.getByText("unknown")).toBeInTheDocument();
  });

  test("exposes a delete control that opens a confirm dialog", () => {
    render(wrap(<McpServerCard resource={stdioServer} />));
    fireEvent.click(screen.getByRole("button", { name: /delete server/i }));
    expect(screen.getByText(/Delete mcp_server:fs/)).toBeInTheDocument();
  });

  test("shows a status badge when the backend reports a known status", async () => {
    mockApi("failing");
    render(wrap(<McpServerCard resource={stdioServer} />));
    expect(await screen.findByTestId("health-badge")).toBeInTheDocument();
  });

  test("shows no status badge when the status is unknown", async () => {
    mockApi("unknown");
    render(wrap(<McpServerCard resource={stdioServer} />));
    expect(await screen.findByText("stdio")).toBeInTheDocument();
    expect(screen.queryByTestId("health-badge")).not.toBeInTheDocument();
  });
});
