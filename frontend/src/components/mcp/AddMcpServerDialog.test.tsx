// frontend/src/components/mcp/AddMcpServerDialog.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route, useParams } from "react-router-dom";
import { AddMcpServerDialog } from "./AddMcpServerDialog";

vi.mock("@/lib/api/client", () => ({
  getApiClient: vi.fn(),
}));

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

/**
 * Stands in for the server's detail page and echoes the segment the router
 * matched, so the assertions can check WHICH identifier the dialog followed.
 * The route is `:uid`: there is no name→uid redirect any more, so a dialog that
 * navigated to the name would land on a page that resolves nothing.
 */
function DetailProbe() {
  const { uid } = useParams<{ uid: string }>();
  return <div data-testid="detail-page">{uid}</div>;
}

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/mcp-servers"]}>
        <Routes>
          <Route path="/mcp-servers" element={<AddMcpServerDialog />} />
          <Route path="/mcp-servers/:uid" element={<DetailProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const SAMPLE = JSON.stringify({ mcpServers: { fs: { command: "npx" } } });

function openJsonTab() {
  fireEvent.click(screen.getByRole("button", { name: /add mcp server/i }));
}

function openAndReview() {
  openJsonTab();
  fireEvent.change(screen.getByLabelText("MCP server JSON"), {
    target: { value: SAMPLE },
  });
  fireEvent.click(screen.getByRole("button", { name: /continue/i }));
}

describe("AddMcpServerDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("renders the JSON import panel", () => {
    getApiClientMock.mockReturnValue({
      POST: vi.fn(),
    } as unknown as ReturnType<typeof getApiClient>);
    render(wrap());
    expect(screen.queryByLabelText("MCP server JSON")).not.toBeInTheDocument();
    openJsonTab();
    expect(screen.getByLabelText("MCP server JSON")).toBeInTheDocument();
  });

  test("imports a pasted server and navigates to its detail page BY UID", async () => {
    const postMock = vi.fn().mockResolvedValue({
      data: {
        uid: "u-filesystem",
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

    // The pasted document called it "fs"; the URL has to carry the uid the
    // registration answered with, which is what survives a later rename.
    await waitFor(() => {
      expect(screen.getByTestId("detail-page")).toHaveTextContent("u-filesystem");
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
              uid: "u-github",
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
    openJsonTab();
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
      expect(screen.getByTestId("detail-page")).toHaveTextContent("u-github");
    });

    // Resource is registered before the credential store is written (no orphans).
    expect(postMock.mock.calls.map((c) => c[0])).toEqual(["/resources", "/credentials"]);
    // The secret goes to the encrypted credential store; the config keeps only a
    // ref, and the ref is opaque: `mcp_server/<uuid4 hex>/<env key>`. It used to
    // be `<server name>.<env key>`, which made the server's name a key into the
    // store — survivable only while an mcp_server could not be renamed. What is
    // asserted is the shape plus the pairing, because there is no value a test
    // could name, and the pairing is the part that matters.
    const keychainCall = postMock.mock.calls.find((c) => c[0] === "/credentials");
    const ref = keychainCall?.[1].body.ref;
    expect(keychainCall?.[1].body).toEqual({
      ref: expect.stringMatching(/^mcp_server\/[0-9a-f]{32}\/GITHUB_TOKEN$/),
      value: "ghp_secret",
    });
    expect(ref).not.toContain("gh.");
    const resourceCall = postMock.mock.calls.find((c) => c[0] === "/resources");
    const transport = resourceCall?.[1].body.config.transport;
    expect(transport.credential_refs).toEqual({ GITHUB_TOKEN: ref });
    expect(transport.env).toEqual({});
  });

  test("keeps a non-secret env var on an http server as a header", async () => {
    const postMock = vi.fn().mockResolvedValue({
      data: {
        uid: "u-example-api",
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
    openJsonTab();
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
      expect(screen.getByTestId("detail-page")).toHaveTextContent("u-example-api");
    });

    // HttpTransport has no `env` field; a non-secret env value must be
    // preserved as a header rather than silently dropped.
    const resourceCall = postMock.mock.calls.find((c) => c[0] === "/resources");
    const transport = resourceCall?.[1].body.config.transport;
    expect(transport.type).toBe("http");
    expect(transport.headers).toEqual({ REGION: "us-east" });
    expect(transport).not.toHaveProperty("env");
  });

  test("routes a pasted http server's secret header to a credential ref and a plain one to headers", async () => {
    const postMock = vi.fn().mockResolvedValue({
      data: {
        uid: "u-example-api",
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
    openJsonTab();
    fireEvent.change(screen.getByLabelText("MCP server JSON"), {
      target: {
        value: JSON.stringify({
          mcpServers: {
            api: {
              url: "https://example.com/mcp",
              headers: { Authorization: "Bearer abc", "X-Region": "us-east" },
            },
          },
        }),
      },
    });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    fireEvent.click(await screen.findByRole("button", { name: /import/i }));
    await waitFor(() => {
      expect(screen.getByTestId("detail-page")).toHaveTextContent("u-example-api");
    });

    const resourceCall = postMock.mock.calls.find((c) => c[0] === "/resources");
    const transport = resourceCall?.[1].body.config.transport;
    expect(transport.headers).toEqual({ "X-Region": "us-east" });
    const ref = transport.credential_refs.Authorization;
    expect(typeof ref).toBe("string");
    const credentialCall = postMock.mock.calls.find((c) => c[0] === "/credentials");
    expect(credentialCall?.[1].body).toEqual({ ref, value: "Bearer abc" });
  });
});
