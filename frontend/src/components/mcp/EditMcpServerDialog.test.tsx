// frontend/src/components/mcp/EditMcpServerDialog.test.tsx
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

// The uid is identity, the name is the label. They are deliberately different
// strings here: the PATCH is addressed to the uid while the credential refs the
// save mints still spell the NAME, and only distinct values can tell the two
// apart.
const stdioResource: ResourceOut = {
  uid: "u-github",
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
  uid: "u-filesystem",
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

  test("timeouts are editable fields, defaulted, and saved back into config", async () => {
    // They were configurable on the backend and had no UI at all, so every
    // server ran on the defaults regardless of how slow its upstream was.
    const patch = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({
      PATCH: patch,
      POST: vi.fn().mockResolvedValue({ data: {}, error: undefined }),
      DELETE: vi.fn().mockResolvedValue({ data: undefined, error: undefined }),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<EditMcpServerDialog resource={noCredsResource} />));
    openDialog();

    // A server that never set one shows the backend default, not an empty box.
    const request = screen.getByLabelText(/^request$/i) as HTMLInputElement;
    expect(request.value).toBe("120");
    expect((screen.getByLabelText(/^spawn$/i) as HTMLInputElement).value).toBe("30");
    // Two fields, not three: the idle timeout is gone with the backend field,
    // which nothing ever enforced.
    expect(screen.queryByLabelText(/^idle$/i)).toBeNull();

    // The JSON textarea must not ALSO carry them — two controls over one key
    // would fight on save.
    const textarea = screen.getByRole("textbox", { name: /config/i }) as HTMLTextAreaElement;
    expect(textarea.value).not.toContain("request_timeout_seconds");

    fireEvent.change(request, { target: { value: "45" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(patch).toHaveBeenCalled());
    const body = patch.mock.calls[0][1].body as { config: Record<string, unknown> };
    expect(body.config.request_timeout_seconds).toBe(45);
    expect(body.config.spawn_timeout_seconds).toBe(30);
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

    // Credential store POST should NOT be called (value is empty)
    expect(postMock).not.toHaveBeenCalledWith("/credentials", expect.anything());

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

    // Credential store write must happen before resource PATCH
    const keychainIdx = callOrder.indexOf("POST:/credentials");
    const patchIdx = callOrder.findIndex((c) => c.startsWith("PATCH:"));
    expect(keychainIdx).toBeGreaterThanOrEqual(0);
    expect(patchIdx).toBeGreaterThanOrEqual(0);
    expect(keychainIdx).toBeLessThan(patchIdx);

    // Credential store payload has the correct ref and value
    const keychainCall = postMock.mock.calls.find((c) => c[0] === "/credentials");
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

  test("PATCHes /resources/{uid} while the credential refs it mints spell the NAME", async () => {
    // The two halves of the identity split meet in this one save: the request
    // is routed by the uid (so it keeps resolving after a rename), and the ref
    // written into the credential store keeps the `<name>.` spelling every
    // already-stored ref uses — this dialog holds no plaintext to migrate them
    // with, which is also why it offers no rename.
    const patchMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({
      PATCH: patchMock,
      POST: postMock,
      DELETE: vi.fn().mockResolvedValue({ data: undefined, error: undefined }),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<EditMcpServerDialog resource={stdioResource} />));
    openDialog();

    const passwordInputs = screen.getAllByPlaceholderText(/Leave blank to keep/i);
    fireEvent.change(passwordInputs[0], { target: { value: "rotated" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(patchMock).toHaveBeenCalled());

    // No kind segment: a uid already names exactly one row.
    expect(patchMock).toHaveBeenCalledWith(
      "/resources/{uid}",
      expect.objectContaining({ params: { path: { uid: "u-github" } } }),
    );
    expect(postMock.mock.calls.find((c) => c[0] === "/credentials")?.[1].body).toEqual({
      ref: "gh.GITHUB_TOKEN",
      value: "rotated",
    });
  });
});
