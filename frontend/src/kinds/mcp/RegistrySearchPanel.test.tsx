// frontend/src/kinds/mcp/RegistrySearchPanel.test.tsx
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

const INSTALLABLE = {
  name: "io.github.acme/gh",
  title: "GitHub",
  description: "GitHub MCP server",
  version: "1.0.0",
  registry_type: "npm",
  transport_type: "stdio",
  installable: true,
  homepage: null,
  draft: {
    transport_type: "stdio",
    command: "npx",
    args: ["-y", "@acme/gh"],
    url: "",
    env: [
      { key: "GITHUB_TOKEN", is_secret: true, required: true, description: "A PAT" },
      { key: "GH_REGION", is_secret: false, required: false, description: null },
    ],
  },
};

const NON_INSTALLABLE = {
  name: "io.github.acme/manual",
  title: "Manual Server",
  description: "Needs manual setup",
  version: null,
  registry_type: null,
  transport_type: "http",
  installable: false,
  homepage: "https://example.com/docs",
  draft: null,
};

function openSearchTab() {
  fireEvent.click(screen.getByRole("button", { name: /add mcp server/i }));
  // The dialog defaults to the Paste-JSON tab; activate the registry-search
  // tab (Radix tabs switch on mouseDown, not synthetic click).
  fireEvent.mouseDown(screen.getByRole("tab", { name: /search registry/i }));
}

describe("RegistrySearchPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("searches and renders results", async () => {
    const getMock = vi
      .fn()
      .mockResolvedValue({ data: { servers: [INSTALLABLE, NON_INSTALLABLE] }, error: undefined });
    getApiClientMock.mockReturnValue({
      GET: getMock,
      POST: vi.fn(),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap());
    openSearchTab();
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "github" } });
    fireEvent.click(screen.getByRole("button", { name: /^search$/i }));

    expect(await screen.findByText("GitHub")).toBeInTheDocument();
    expect(screen.getByText("Manual Server")).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith("/mcp-registry/search", {
      params: { query: { q: "github", limit: 30 } },
    });
  });

  test("a non-installable entry has no Use button but shows a homepage link", async () => {
    const getMock = vi
      .fn()
      .mockResolvedValue({ data: { servers: [NON_INSTALLABLE] }, error: undefined });
    getApiClientMock.mockReturnValue({
      GET: getMock,
      POST: vi.fn(),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap());
    openSearchTab();
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: /^search$/i }));

    await screen.findByText("Manual Server");
    expect(screen.queryByRole("button", { name: /^use$/i })).not.toBeInTheDocument();
    expect(screen.getByText(/not auto-installable/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /homepage/i })).toHaveAttribute(
      "href",
      "https://example.com/docs",
    );
  });

  test("Use → fills env form → Add calls the registration path with a ParsedServer", async () => {
    const getMock = vi
      .fn()
      .mockResolvedValue({ data: { servers: [INSTALLABLE] }, error: undefined });
    const postMock = vi.fn().mockImplementation((path: string) =>
      path === "/credentials"
        ? Promise.resolve({ data: undefined, error: undefined })
        : Promise.resolve({
            data: {
              ref: "mcp_server:io.github.acme-gh",
              kind: "mcp_server",
              name: "io.github.acme-gh",
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
      GET: getMock,
      POST: postMock,
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap());
    openSearchTab();
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "github" } });
    fireEvent.click(screen.getByRole("button", { name: /^search$/i }));

    fireEvent.click(await screen.findByRole("button", { name: /^use$/i }));

    // Name seeded from the sanitized registry id (slash → hyphen).
    const nameInput = screen.getByLabelText("Name") as HTMLInputElement;
    expect(nameInput.value).toBe("io.github.acme-gh");

    fireEvent.change(screen.getByLabelText(/GITHUB_TOKEN/), {
      target: { value: "ghp_xyz" },
    });
    fireEvent.click(screen.getByRole("button", { name: /add server/i }));

    await waitFor(() => {
      expect(screen.getByTestId("detail-page")).toBeInTheDocument();
    });

    // Resource registered before the secret is written to the credential store.
    expect(postMock.mock.calls.map((c) => c[0])).toEqual(["/resources", "/credentials"]);
    const resourceCall = postMock.mock.calls.find((c) => c[0] === "/resources");
    expect(resourceCall?.[1].body.name).toBe("io.github.acme-gh");
    const transport = resourceCall?.[1].body.config.transport;
    expect(transport.type).toBe("stdio");
    expect(transport.command).toBe("npx");
    expect(transport.args).toEqual(["-y", "@acme/gh"]);
    // Secret → credential ref; non-secret blank value stays inline in env.
    expect(transport.credential_refs).toEqual({
      GITHUB_TOKEN: "io.github.acme-gh.GITHUB_TOKEN",
    });
    expect(transport.env).toEqual({ GH_REGION: "" });
    const credCall = postMock.mock.calls.find((c) => c[0] === "/credentials");
    expect(credCall?.[1].body).toEqual({
      ref: "io.github.acme-gh.GITHUB_TOKEN",
      value: "ghp_xyz",
    });
  });

  test("a 502 shows the unavailable message", async () => {
    const getMock = vi.fn().mockResolvedValue({
      data: undefined,
      error: { error: { code: "REGISTRY_UNAVAILABLE", message: "registry down" } },
    });
    getApiClientMock.mockReturnValue({
      GET: getMock,
      POST: vi.fn(),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap());
    openSearchTab();
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: /^search$/i }));

    expect(await screen.findByText(/registry is unavailable/i)).toBeInTheDocument();
  });
});
