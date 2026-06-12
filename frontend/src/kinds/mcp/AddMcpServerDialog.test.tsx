// frontend/src/kinds/mcp/AddMcpServerDialog.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { AddMcpServerDialog } from "./AddMcpServerDialog";

vi.mock("@/lib/api/client", () => ({
  getApiClient: vi.fn(),
}));

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/mcp-servers"]}>
        <Routes>
          <Route path="/mcp-servers" element={<AddMcpServerDialog />} />
          <Route
            path="/mcp-servers/mcp_server/:name"
            element={<div data-testid="detail-page">detail</div>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const SAMPLE = JSON.stringify({ mcpServers: { fs: { command: "npx" } } });

function openAndReview() {
  fireEvent.click(screen.getByRole("button", { name: /add mcp server/i }));
  fireEvent.change(screen.getByLabelText("MCP server JSON"), {
    target: { value: SAMPLE },
  });
  fireEvent.click(screen.getByRole("button", { name: /continue/i }));
}

describe("AddMcpServerDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("opens the JSON import panel when the trigger is clicked", () => {
    getApiClientMock.mockReturnValue({
      POST: vi.fn(),
    } as unknown as ReturnType<typeof getApiClient>);
    render(wrap());
    expect(screen.queryByLabelText("MCP server JSON")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /add mcp server/i }));
    expect(screen.getByLabelText("MCP server JSON")).toBeInTheDocument();
  });

  test("imports a pasted server and navigates to its detail page", async () => {
    const postMock = vi.fn().mockResolvedValue({
      data: {
        ref: "mcp_server:fs",
        kind: "mcp_server",
        name: "fs",
        description: null,
        config: {},
        enabled: true,
        created_at: "2026-05-21T00:00:00Z",
        updated_at: "2026-05-21T00:00:00Z",
      },
      error: undefined,
    });
    getApiClientMock.mockReturnValue({
      POST: postMock,
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap());
    openAndReview();
    fireEvent.click(await screen.findByRole("button", { name: /import/i }));

    await waitFor(() => {
      expect(screen.getByTestId("detail-page")).toBeInTheDocument();
    });
  });

  test("shows an error callout when the API rejects the import", async () => {
    const postMock = vi.fn().mockResolvedValue({
      data: undefined,
      error: { error: { code: "CONFLICT", message: "already exists" } },
    });
    getApiClientMock.mockReturnValue({
      POST: postMock,
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap());
    openAndReview();
    fireEvent.click(await screen.findByRole("button", { name: /import/i }));

    await waitFor(() => {
      expect(screen.getByText(/already exists/)).toBeInTheDocument();
    });
  });

  test("lifts a secret env var into the keychain, storing only a ref", async () => {
    const postMock = vi.fn().mockImplementation((path: string) =>
      path === "/credentials"
        ? Promise.resolve({ data: undefined, error: undefined })
        : Promise.resolve({
            data: {
              ref: "mcp_server:gh",
              kind: "mcp_server",
              name: "gh",
              description: null,
              config: {},
              enabled: true,
              created_at: "2026-05-21T00:00:00Z",
              updated_at: "2026-05-21T00:00:00Z",
            },
            error: undefined,
          }),
    );
    getApiClientMock.mockReturnValue({
      POST: postMock,
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap());
    fireEvent.click(screen.getByRole("button", { name: /add mcp server/i }));
    fireEvent.change(screen.getByLabelText("MCP server JSON"), {
      target: {
        value: JSON.stringify({
          mcpServers: {
            gh: { command: "npx", env: { GITHUB_TOKEN: "ghp_secret" } },
          },
        }),
      },
    });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    fireEvent.click(await screen.findByRole("button", { name: /import/i }));
    await waitFor(() => {
      expect(screen.getByTestId("detail-page")).toBeInTheDocument();
    });

    // Resource is registered before the credential store is written (no orphans).
    expect(postMock.mock.calls.map((c) => c[0])).toEqual(["/resources", "/credentials"]);
    // The secret goes to the encrypted credential store; the config keeps only a ref.
    const keychainCall = postMock.mock.calls.find((c) => c[0] === "/credentials");
    expect(keychainCall?.[1].body).toEqual({
      ref: "gh.GITHUB_TOKEN",
      value: "ghp_secret",
    });
    const resourceCall = postMock.mock.calls.find((c) => c[0] === "/resources");
    const transport = resourceCall?.[1].body.config.transport;
    expect(transport.credential_refs).toEqual({
      GITHUB_TOKEN: "gh.GITHUB_TOKEN",
    });
    expect(transport.env).toEqual({});
  });

  test("keeps a non-secret env var on an http server as a header", async () => {
    const postMock = vi.fn().mockResolvedValue({
      data: {
        ref: "mcp_server:api",
        kind: "mcp_server",
        name: "api",
        description: null,
        config: {},
        enabled: true,
        created_at: "2026-05-21T00:00:00Z",
        updated_at: "2026-05-21T00:00:00Z",
      },
      error: undefined,
    });
    getApiClientMock.mockReturnValue({
      POST: postMock,
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap());
    fireEvent.click(screen.getByRole("button", { name: /add mcp server/i }));
    fireEvent.change(screen.getByLabelText("MCP server JSON"), {
      target: {
        value: JSON.stringify({
          mcpServers: {
            api: { url: "https://example.com/mcp", env: { REGION: "us-east" } },
          },
        }),
      },
    });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    fireEvent.click(await screen.findByRole("button", { name: /import/i }));
    await waitFor(() => {
      expect(screen.getByTestId("detail-page")).toBeInTheDocument();
    });

    // HttpTransport has no `env` field; a non-secret env value must be
    // preserved as a header rather than silently dropped.
    const resourceCall = postMock.mock.calls.find((c) => c[0] === "/resources");
    const transport = resourceCall?.[1].body.config.transport;
    expect(transport.type).toBe("http");
    expect(transport.headers).toEqual({ REGION: "us-east" });
    expect(transport).not.toHaveProperty("env");
  });
});
