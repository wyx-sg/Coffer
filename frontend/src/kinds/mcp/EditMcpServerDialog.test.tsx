// frontend/src/kinds/mcp/EditMcpServerDialog.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { EditMcpServerDialog } from "./EditMcpServerDialog";
import type { components } from "@/lib/api/types";

vi.mock("@/lib/api/client", () => ({
  getApiClient: vi.fn(),
}));

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

type ResourceOut = components["schemas"]["ResourceOut"];

const stdioResource: ResourceOut = {
  ref: "mcp_server:gh",
  kind: "mcp_server",
  name: "gh",
  description: "GitHub MCP",
  config: {
    transport: {
      type: "stdio",
      command: "npx",
      credential_refs: { GITHUB_TOKEN: "gh.GITHUB_TOKEN" },
    },
  },
  enabled: true,
  created_at: "2026-05-21T00:00:00Z",
  updated_at: "2026-05-21T00:00:00Z",
};

const noCredsResource: ResourceOut = {
  ref: "mcp_server:fs",
  kind: "mcp_server",
  name: "fs",
  description: "Filesystem MCP",
  config: {
    transport: { type: "stdio", command: "npx" },
  },
  enabled: true,
  created_at: "2026-05-21T00:00:00Z",
  updated_at: "2026-05-21T00:00:00Z",
};

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

function openDialog() {
  fireEvent.click(screen.getByRole("button", { name: /edit/i }));
}

describe("EditMcpServerDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("renders existing description and config when opened", () => {
    getApiClientMock.mockReturnValue({
      PATCH: vi.fn().mockResolvedValue({ data: {}, error: undefined }),
      POST: vi.fn().mockResolvedValue({ data: {}, error: undefined }),
      DELETE: vi.fn().mockResolvedValue({ data: undefined, error: undefined }),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<EditMcpServerDialog resource={stdioResource} />));
    openDialog();

    const descInput = screen.getByLabelText(/description/i);
    expect((descInput as HTMLInputElement).value).toBe("GitHub MCP");
    // Config textarea is shown (without credential_refs)
    const textarea = screen.getByRole("textbox", { name: /config/i });
    const configVal = (textarea as HTMLTextAreaElement).value;
    expect(configVal).toContain("stdio");
    expect(configVal).not.toContain("credential_refs");
  });

  test("pre-populates existing credential rows with keep-existing placeholder", () => {
    getApiClientMock.mockReturnValue({
      PATCH: vi.fn(),
      POST: vi.fn(),
      DELETE: vi.fn(),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<EditMcpServerDialog resource={stdioResource} />));
    openDialog();

    // The credential name field shows the env var name
    const nameInputs = screen.getAllByPlaceholderText("GITHUB_TOKEN");
    expect(nameInputs.length).toBeGreaterThanOrEqual(1);
    // The value field shows the "keep existing" placeholder
    const passwordInputs = screen.getAllByPlaceholderText(/Leave blank to keep/i);
    expect(passwordInputs.length).toBeGreaterThanOrEqual(1);
  });

  test("adds a new credential row when the add button is clicked", () => {
    getApiClientMock.mockReturnValue({
      PATCH: vi.fn(),
      POST: vi.fn(),
      DELETE: vi.fn(),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<EditMcpServerDialog resource={noCredsResource} />));
    openDialog();

    // No credentials initially
    expect(screen.queryByPlaceholderText("GITHUB_TOKEN")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /add credential/i }));

    // Now there should be an input row
    expect(screen.getByPlaceholderText("GITHUB_TOKEN")).toBeInTheDocument();
  });

  test("removes a credential row when the remove button is clicked", () => {
    getApiClientMock.mockReturnValue({
      PATCH: vi.fn(),
      POST: vi.fn(),
      DELETE: vi.fn(),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<EditMcpServerDialog resource={stdioResource} />));
    openDialog();

    // Start with one credential row
    expect(screen.getByPlaceholderText("GITHUB_TOKEN")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /remove credential/i }));

    // Credential row is gone
    expect(screen.queryByPlaceholderText("GITHUB_TOKEN")).not.toBeInTheDocument();
  });

  test("keep-existing path: leaves value='' for unchanged creds, PATCH still has ref in credential_refs", async () => {
    const patchMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    const deleteMock = vi.fn().mockResolvedValue({ data: undefined, error: undefined });
    getApiClientMock.mockReturnValue({
      PATCH: patchMock,
      POST: postMock,
      DELETE: deleteMock,
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<EditMcpServerDialog resource={stdioResource} />));
    openDialog();

    // Don't change the credential value — keep the placeholder ("keep existing")
    // Save immediately
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => {
      expect(patchMock).toHaveBeenCalled();
    });

    // Keychain POST should NOT be called (value is empty)
    expect(postMock).not.toHaveBeenCalledWith("/keychain", expect.anything());

    // PATCH body should still contain the original ref for GITHUB_TOKEN
    const patchArgs = patchMock.mock.calls[0];
    const body = patchArgs[1].body as {
      config: { transport: { credential_refs: Record<string, string> } };
    };
    expect(body.config.transport.credential_refs).toEqual({
      GITHUB_TOKEN: "gh.GITHUB_TOKEN",
    });
  });

  test("on save with a NEW credential value, keychain write fires BEFORE the resource PATCH", async () => {
    const callOrder: string[] = [];
    const postMock = vi.fn().mockImplementation((path: string) => {
      callOrder.push(`POST:${path}`);
      return Promise.resolve({ data: {}, error: undefined });
    });
    const patchMock = vi.fn().mockImplementation((path: string) => {
      callOrder.push(`PATCH:${path}`);
      return Promise.resolve({ data: {}, error: undefined });
    });
    getApiClientMock.mockReturnValue({
      POST: postMock,
      PATCH: patchMock,
      DELETE: vi.fn().mockResolvedValue({ data: undefined, error: undefined }),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<EditMcpServerDialog resource={stdioResource} />));
    openDialog();

    // Set a new value for the existing credential
    const passwordInputs = screen.getAllByPlaceholderText(/Leave blank to keep/i);
    fireEvent.change(passwordInputs[0], { target: { value: "new-secret-token" } });

    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => {
      expect(patchMock).toHaveBeenCalled();
    });

    // Keychain write must happen before resource PATCH
    const keychainIdx = callOrder.indexOf("POST:/keychain");
    const patchIdx = callOrder.findIndex((c) => c.startsWith("PATCH:"));
    expect(keychainIdx).toBeGreaterThanOrEqual(0);
    expect(patchIdx).toBeGreaterThanOrEqual(0);
    expect(keychainIdx).toBeLessThan(patchIdx);

    // Keychain payload has the correct ref and value
    const keychainCall = postMock.mock.calls.find((c) => c[0] === "/keychain");
    expect(keychainCall?.[1].body).toEqual({
      ref: "gh.GITHUB_TOKEN",
      value: "new-secret-token",
    });

    // PATCH body includes the ref
    const patchArgs = patchMock.mock.calls[0];
    const body = patchArgs[1].body as {
      config: { transport: { credential_refs: Record<string, string> } };
    };
    expect(body.config.transport.credential_refs).toEqual({
      GITHUB_TOKEN: "gh.GITHUB_TOKEN",
    });
  });
});
